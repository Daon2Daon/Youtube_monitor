import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { instantApi, promptApi, videoApi } from '../api/client'
const PLACEHOLDER = 'https://www.youtube.com/watch?v=...'

type Phase = 'idle' | 'loading' | 'analyzing' | 'done' | 'error'

export default function InstantAnalyze() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [message, setMessage] = useState('')
  const [promptOpen, setPromptOpen] = useState(false)
  const [customPrompt, setCustomPrompt] = useState('')
  const [promptLoaded, setPromptLoaded] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  const handlePromptToggle = async () => {
    const next = !promptOpen
    setPromptOpen(next)
    if (next && !promptLoaded) {
      try {
        const res = await promptApi.get()
        setCustomPrompt(res.analysis_prompt)
        setPromptLoaded(true)
      } catch { /* 기본 프롬프트 로드 실패 무시 */ }
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return

    setPhase('loading')
    setMessage('')
    stopPolling()

    try {
      const res = await instantApi.analyze(
        url.trim(),
        promptOpen && customPrompt ? customPrompt : undefined,
      )

      setMessage(res.message)

      if (res.existing) {
        // 이미 존재하는 영상 → 잠시 후 이동
        setPhase('done')
        setTimeout(() => navigate(`/videos/${res.video_pk}`), 1200)
        return
      }

      // 신규: 분석 완료 대기 폴링
      setPhase('analyzing')
      const videoPk = res.video_pk
      pollingRef.current = setInterval(async () => {
        try {
          const detail = await videoApi.get(videoPk)
          if (detail.analysis_status === 'done' || detail.analysis_status === 'failed') {
            stopPolling()
            setPhase('done')
            setTimeout(() => navigate(`/videos/${videoPk}`), 800)
          }
        } catch { /* 폴링 실패 무시 */ }
      }, 3000)

      // 최대 5분 대기 후 강제 이동
      setTimeout(() => {
        if (pollingRef.current) {
          stopPolling()
          setPhase('done')
          navigate(`/videos/${videoPk}`)
        }
      }, 5 * 60 * 1000)

    } catch (err) {
      setPhase('error')
      setMessage((err as Error).message)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">영상 분석</h1>
        <p className="mt-1 text-sm text-gray-500">
          채널 등록 없이 YouTube URL을 직접 입력해 분석합니다.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm p-6 space-y-4">
        {/* URL 입력 */}
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700">YouTube URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={PLACEHOLDER}
            disabled={phase === 'loading' || phase === 'analyzing'}
            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
          />
          <p className="text-xs text-gray-400">
            watch?v=, youtu.be/, /shorts/ 형식 지원
          </p>
        </div>

        {/* 프롬프트 수정 토글 */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={handlePromptToggle}
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            {promptOpen ? '프롬프트 접기' : '분석 프롬프트 수정 (선택)'}
          </button>

          {promptOpen && (
            <div className="border border-amber-200 rounded-lg bg-amber-50 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-amber-700">
                  이 영상 전용 프롬프트
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const res = await promptApi.get()
                      setCustomPrompt(res.analysis_prompt)
                    } catch { /* no-op */ }
                  }}
                  className="text-xs text-amber-600 hover:text-amber-800 underline"
                >
                  기본값으로 되돌리기
                </button>
              </div>
              <textarea
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                rows={8}
                className="w-full border border-amber-300 rounded-lg px-3 py-2 text-xs font-mono bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 resize-y"
                spellCheck={false}
              />
              <p className="text-xs text-amber-600">
                변수:{' '}
                <code className="bg-amber-100 px-1 rounded">{'{channel_name}'}</code>{' '}
                <code className="bg-amber-100 px-1 rounded">{'{published_at_kst}'}</code>{' '}
                <code className="bg-amber-100 px-1 rounded">{'{video_url}'}</code>
              </p>
            </div>
          )}
        </div>

        {/* 상태 메시지 */}
        {message && (
          <div
            className={`text-sm rounded-lg px-4 py-3 ${
              phase === 'error'
                ? 'bg-red-50 text-red-700 border border-red-200'
                : 'bg-blue-50 text-blue-700 border border-blue-100'
            }`}
          >
            {message}
          </div>
        )}

        {/* 분석 중 진행 표시 */}
        {phase === 'analyzing' && (
          <div className="flex items-center gap-3 text-sm text-gray-600 bg-gray-50 rounded-lg px-4 py-3">
            <svg className="animate-spin w-5 h-5 text-blue-500 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span>LLM 분석 중입니다. 완료되면 결과 페이지로 이동합니다...</span>
          </div>
        )}

        {/* 제출 버튼 */}
        <button
          type="submit"
          disabled={!url.trim() || phase === 'loading' || phase === 'analyzing'}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
        >
          {phase === 'loading'
            ? '영상 정보 조회 중...'
            : phase === 'analyzing'
            ? '분석 중...'
            : '분석 시작'}
        </button>
      </form>

      {/* 안내 */}
      <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-500 space-y-1.5">
        <p className="font-medium text-gray-700">안내</p>
        <ul className="list-disc list-inside space-y-1">
          <li>분석은 일반 채널 영상과 동일한 파이프라인으로 진행됩니다.</li>
          <li>이미 분석된 URL을 입력하면 기존 결과 페이지로 이동합니다.</li>
          <li>추가 영상은 알림(텔레그램)이 발송되지 않습니다.</li>
          <li>분석 결과는 영상 목록에서 확인하거나 재분석할 수 있습니다.</li>
        </ul>
      </div>
    </div>
  )
}
