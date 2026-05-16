import { useEffect, useState } from 'react'
import { promptApi } from '../../api/client'
import type { PromptSettings } from '../../api/client'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

type SaveState = 'idle' | 'saving' | 'ok' | 'fail'

const PROMPT_HELP = `사용 가능한 변수:
  {today}             오늘 날짜 (KST)
  {channel_name}      브랜드/채널명
  {published_at_kst}  업로드 일시 (KST)
  {video_url}         유튜브 영상 URL (Fallback 모델용)`

export default function PromptSettings() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<PromptSettings | null>(null)

  const [draft, setDraft] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [saveMsg, setSaveMsg] = useState('')
  const [resetConfirm, setResetConfirm] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await promptApi.get()
      setData(res)
      setDraft(res.analysis_prompt)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSave = async () => {
    setSaveState('saving')
    setSaveMsg('')
    try {
      const res = await promptApi.update({ analysis_prompt: draft })
      setData(res)
      setDraft(res.analysis_prompt)
      setSaveState('ok')
      setSaveMsg('저장되었습니다.')
    } catch (e) {
      setSaveState('fail')
      setSaveMsg((e as Error).message)
    }
  }

  const handleReset = async () => {
    if (!resetConfirm) {
      setResetConfirm(true)
      return
    }
    setSaveState('saving')
    setSaveMsg('')
    setResetConfirm(false)
    try {
      const res = await promptApi.reset()
      setData(res)
      setDraft(res.analysis_prompt)
      setSaveState('ok')
      setSaveMsg('기본값으로 초기화되었습니다.')
    } catch (e) {
      setSaveState('fail')
      setSaveMsg((e as Error).message)
    }
  }

  const isDirty = data !== null && draft !== data.analysis_prompt

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">프롬프트</h1>
          <p className="text-sm text-gray-500 mt-1">
            경쟁사 광고·프로모션 영상 분석용 단일 프롬프트입니다. Primary·Fallback 모델 모두 동일한 내용을 사용합니다.
            버전: <span className="font-mono text-blue-600">{data?.prompt_version}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saveState === 'ok' && (
            <span className="text-sm text-green-600 font-medium">{saveMsg}</span>
          )}
          {saveState === 'fail' && (
            <span className="text-sm text-red-600">{saveMsg}</span>
          )}
          <button
            type="button"
            onClick={handleReset}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              resetConfirm
                ? 'bg-red-600 text-white border-red-600 hover:bg-red-700'
                : 'border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {resetConfirm ? '확인: 초기화' : '기본값으로 초기화'}
          </button>
          {resetConfirm && (
            <button
              type="button"
              onClick={() => setResetConfirm(false)}
              className="px-3 py-1.5 rounded-lg text-sm border border-gray-300 text-gray-600 hover:bg-gray-50"
            >
              취소
            </button>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!isDirty || saveState === 'saving'}
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saveState === 'saving' ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <p className="text-sm font-semibold text-blue-700 mb-1">프롬프트 템플릿 변수</p>
        <pre className="text-xs text-blue-600 font-mono whitespace-pre-wrap">{PROMPT_HELP}</pre>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">분석 프롬프트</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            JSON 출력 형식과 브랜드 톤앤매너(trendy/trustworthy/premium/humorous) 필드를 유지해 주세요.
          </p>
        </div>
        <textarea
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            if (saveState === 'ok') setSaveState('idle')
          }}
          rows={28}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder="분석 프롬프트를 입력하세요..."
          spellCheck={false}
        />
      </div>
    </div>
  )
}
