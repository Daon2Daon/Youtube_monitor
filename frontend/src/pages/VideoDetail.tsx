import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import dayjs from 'dayjs'
import { videoApi, promptApi } from '../api/client'
import type { VideoDetail as VideoDetailType } from '../api/client'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'
import StatusBadge from '../components/StatusBadge'
function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = score >= 0.7 ? 'bg-green-500' : score >= 0.4 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

export default function VideoDetail() {
  const { videoPk } = useParams<{ videoPk: string }>()
  const navigate = useNavigate()
  const [video, setVideo] = useState<VideoDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 커스텀 프롬프트 패널
  const [promptOpen, setPromptOpen] = useState(false)
  const [customPrompt, setCustomPrompt] = useState('')
  const [promptLoaded, setPromptLoaded] = useState(false)

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current)
      pollingTimeoutRef.current = null
    }
  }

  const load = async () => {
    if (!videoPk) return
    setLoading(true)
    setError(null)
    try {
      setVideo(await videoApi.get(Number(videoPk)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const silentRefresh = async () => {
    if (!videoPk) return
    try {
      const updated = await videoApi.get(Number(videoPk))
      setVideo(updated)
      if (updated.analysis_status !== 'processing' && updated.analysis_status !== 'pending') {
        stopPolling()
        setReanalyzing(false)
      }
    } catch {
      stopPolling()
      setReanalyzing(false)
    }
  }

  useEffect(() => { load() }, [videoPk])

  useEffect(() => stopPolling, [])

  const handleOpenPrompt = async () => {
    if (!promptLoaded) {
      try {
        const res = await promptApi.get()
        setCustomPrompt(res.analysis_prompt)
        setPromptLoaded(true)
      } catch {
        // 실패해도 빈 텍스트로 열기
        setPromptLoaded(true)
      }
    }
    setPromptOpen((prev) => !prev)
  }

  const handleDelete = async () => {
    if (!videoPk) return
    setDeleting(true)
    stopPolling()
    try {
      await videoApi.remove(Number(videoPk))
      navigate('/videos')
    } catch (e) {
      alert((e as Error).message)
      setDeleting(false)
      setDeleteConfirm(false)
    }
  }

  const handleReanalyze = async () => {
    if (!videoPk) return
    setReanalyzing(true)
    try {
      const prompt = promptOpen && customPrompt.trim() ? customPrompt.trim() : undefined
      await videoApi.reanalyze(Number(videoPk), prompt)
      await silentRefresh()
      pollingRef.current = setInterval(silentRefresh, 2000)
      // 3분 후 주기적 새로고침 자동 중단 (분석이 비정상적으로 오래 걸리는 경우 대비)
      pollingTimeoutRef.current = setTimeout(() => {
        stopPolling()
        setReanalyzing(false)
      }, 3 * 60 * 1000)
    } catch (e) {
      setReanalyzing(false)
      alert((e as Error).message)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!video) return null

  const showTelegramPreview =
    Boolean(video.headline || video.full_analysis_md || (video.bullet_points && video.bullet_points.length > 0))

  return (
    <div className="space-y-5 max-w-3xl mx-auto w-full">
      {/* 상단 네비 */}
      <div className="flex items-center gap-2 text-sm text-gray-500 min-w-0">
        <Link to="/videos" className="hover:text-blue-600 shrink-0">영상 목록</Link>
        <span className="shrink-0">/</span>
        <span className="text-gray-700 truncate min-w-0">{video.title}</span>
      </div>

      <div className="space-y-5">
        {/* 영상 헤더 */}
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            {video.thumbnail_url && (
              <img src={video.thumbnail_url} alt={video.title} className="w-full aspect-video object-cover" />
            )}
            <div className="p-4 sm:p-5 space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <h1 className="text-lg sm:text-xl font-bold text-gray-900 leading-snug min-w-0 flex-1 order-2 sm:order-1">
                  {video.title}
                </h1>
                <div className="flex flex-wrap gap-2 shrink-0 order-1 sm:order-2 sm:justify-end">
                  <a
                    href={video.video_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 font-medium"
                  >
                    YouTube에서 보기
                  </a>
                  <button
                    onClick={handleOpenPrompt}
                    disabled={reanalyzing}
                    className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors disabled:opacity-60 ${
                      promptOpen
                        ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                    title="이 영상 전용 프롬프트를 수정하여 재분석"
                  >
                    {promptOpen ? '프롬프트 닫기' : '프롬프트 수정'}
                  </button>
                  <button
                    onClick={handleReanalyze}
                    disabled={reanalyzing || deleting}
                    className="px-3 py-1.5 bg-blue-50 text-blue-600 text-xs rounded-lg hover:bg-blue-100 disabled:opacity-60 font-medium"
                  >
                    {reanalyzing ? '분석 중...' : promptOpen ? '이 프롬프트로 재분석' : '재분석'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteConfirm(true)}
                    disabled={reanalyzing || deleting}
                    className="px-3 py-1.5 bg-red-50 text-red-500 text-xs rounded-lg hover:bg-red-100 disabled:opacity-60 font-medium"
                  >
                    삭제
                  </button>
                </div>
              </div>

              {/* 커스텀 프롬프트 패널 */}
              {promptOpen && (
                <div className="mt-3 border border-amber-200 rounded-lg bg-amber-50 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-amber-700">
                      이 영상 전용 분석 프롬프트
                      <span className="font-normal text-amber-600 ml-1">(기본 프롬프트 기반으로 편집됨)</span>
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
                    rows={10}
                    className="w-full border border-amber-300 rounded-lg px-3 py-2 text-xs font-mono bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 resize-y"
                    placeholder="분석 프롬프트를 입력하세요..."
                    spellCheck={false}
                  />
                  <p className="text-xs text-amber-600">
                    변수: <code className="bg-amber-100 px-1 rounded">{'{channel_name}'}</code>{' '}
                    <code className="bg-amber-100 px-1 rounded">{'{published_at_kst}'}</code>{' '}
                    <code className="bg-amber-100 px-1 rounded">{'{video_url}'}</code>
                  </p>
                </div>
              )}

              <div className="flex items-center gap-3 flex-wrap text-xs text-gray-500">
                <StatusBadge status={video.analysis_status} />
                {video.source_channel_name && (
                  <span className="text-purple-600 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">
                    추가 · {video.source_channel_name}
                  </span>
                )}
                <span>📅 {dayjs(video.published_at).format('YYYY-MM-DD HH:mm')}</span>
                {video.view_count != null && <span>👁 {video.view_count.toLocaleString()}</span>}
                {video.like_count != null && <span>👍 {video.like_count.toLocaleString()}</span>}
                {video.duration_seconds != null && (
                  <span>⏱ {Math.floor(video.duration_seconds / 60)}분 {video.duration_seconds % 60}초</span>
                )}
              </div>

              {/* 태그 */}
              {video.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {video.tags.map((t) => (
                    <Link
                      key={t}
                      to={`/videos?tag=${encodeURIComponent(t)}`}
                      className="px-2.5 py-0.5 bg-gray-100 hover:bg-blue-50 hover:text-blue-600 text-gray-600 rounded-full text-xs transition-colors"
                    >
                      {t}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* YouTube 원본 설명문 */}
          {video.description && (
            <details className="bg-white rounded-xl shadow-sm p-5 group">
              <summary className="font-semibold text-gray-800 cursor-pointer select-none list-none flex items-center justify-between">
                <span>YouTube 설명문</span>
                <span className="text-gray-400 text-sm group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <pre className="mt-3 text-xs text-gray-600 whitespace-pre-wrap break-words font-sans leading-relaxed max-h-60 overflow-y-auto">
                {video.description}
              </pre>
            </details>
          )}

          {/* 분석 결과 */}
          {video.full_analysis_md ? (
            <div className="bg-white rounded-xl shadow-sm p-4 sm:p-5">
              <h2 className="font-semibold text-gray-800 mb-4">상세 분석</h2>
              <article className="prose prose-sm max-w-none text-gray-700 break-words overflow-x-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{video.full_analysis_md}</ReactMarkdown>
              </article>
            </div>
          ) : video.analysis_status === 'pending' || video.analysis_status === 'processing' ? (
            <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
              <div className="text-4xl mb-2">⏳</div>
              <p>분석이 진행 중입니다...</p>
            </div>
          ) : null}

        {/* 상세 분석 아래: 요약 → 분석 정보 → Telegram 미리보기 → 오류 */}
        {(video.headline ||
          video.one_line ||
          video.short_summary_md ||
          (video.bullet_points && video.bullet_points.length > 0)) && (
          <div className="bg-white rounded-xl shadow-sm p-4 sm:p-5 space-y-3">
            <h2 className="font-semibold text-gray-800">요약</h2>
            {video.headline && (
              <p className="font-medium text-gray-900">{video.headline}</p>
            )}
            {video.one_line && (
              <p className="text-sm text-gray-600 italic">{video.one_line}</p>
            )}
            {video.short_summary_md && (
              <article className="prose prose-sm max-w-none text-gray-700 break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{video.short_summary_md}</ReactMarkdown>
              </article>
            )}
            {video.bullet_points && video.bullet_points.length > 0 && (
              <ul className="space-y-1">
                {video.bullet_points.map((bp, i) => (
                  <li key={i} className="flex gap-2 text-sm text-gray-700">
                    <span className="text-blue-400 shrink-0">•</span>
                    <span className="min-w-0 break-words">{bp}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {(video.sentiment || video.confidence_score != null || video.model_name) && (
          <div className="bg-white rounded-xl shadow-sm p-4 sm:p-5 space-y-3">
            <h2 className="font-semibold text-gray-800">분석 정보</h2>
            {video.sentiment && (
              <div className="flex justify-between gap-4 text-sm min-w-0">
                <span className="text-gray-500 shrink-0">브랜드 톤앤매너</span>
                <span className="font-medium text-gray-700 text-right break-words">{video.sentiment}</span>
              </div>
            )}
            {video.confidence_score != null && (
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">신뢰도</span>
                </div>
                <ConfidenceBar score={video.confidence_score} />
              </div>
            )}
            {video.model_name && (
              <div className="flex justify-between gap-4 text-sm min-w-0">
                <span className="text-gray-500 shrink-0">모델</span>
                <span className="font-medium text-gray-700 text-xs text-right break-all">{video.model_name}</span>
              </div>
            )}
            {video.analyzed_at && (
              <div className="flex justify-between gap-4 text-sm min-w-0">
                <span className="text-gray-500 shrink-0">분석 시각</span>
                <span className="text-gray-700 text-xs shrink-0">{dayjs(video.analyzed_at).format('MM/DD HH:mm')}</span>
              </div>
            )}
          </div>
        )}

        {showTelegramPreview && (
          <div className="bg-gray-800 rounded-xl p-4 text-gray-100 text-xs space-y-2 break-words">
            <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Telegram 알림 미리보기</p>
            <p className="font-bold">
              🎬 [{video.source_channel_name || '모니터 채널'}] 신규 영상
            </p>
            {video.headline && <p className="font-semibold">{video.headline}</p>}
            {video.full_analysis_md && (
              <div className="text-gray-200 whitespace-pre-wrap font-sans leading-relaxed max-h-48 overflow-y-auto border border-gray-600 rounded-lg p-2">
                {video.full_analysis_md.length > 1200
                  ? `${video.full_analysis_md.slice(0, 1200)}…`
                  : video.full_analysis_md}
              </div>
            )}
            {video.bullet_points && video.bullet_points.length > 0 && (
              <ul className="space-y-1 font-sans">
                {video.bullet_points.map((bp, i) => (
                  <li key={i} className="text-gray-200">• {bp}</li>
                ))}
              </ul>
            )}
            {video.tags.length > 0 && (
              <p className="text-blue-300">🏷 {video.tags.slice(0, 8).join(', ')}</p>
            )}
            <p className="text-gray-400 text-[11px]">
              📅 {dayjs(video.published_at).format('YYYY-MM-DD HH:mm')}
              {video.duration_seconds != null && (
                <>
                  {' '}
                  · ⏱ {Math.floor(video.duration_seconds / 60)}분 {video.duration_seconds % 60}초
                </>
              )}
            </p>
            <p className="text-blue-400 underline">🔗 영상 보러가기</p>
            {video.notified_at && (
              <p className="text-green-400 mt-2">✅ 발송됨: {dayjs(video.notified_at).format('MM/DD HH:mm')}</p>
            )}
          </div>
        )}

        {video.analysis_error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-700 space-y-1 break-words">
            <p className="font-semibold">분석 오류</p>
            <p className="font-mono whitespace-pre-wrap">{video.analysis_error}</p>
            <p className="text-gray-500">재시도: {video.retry_count}회</p>
          </div>
        )}
      </div>

      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full space-y-4">
            <h3 className="font-bold text-gray-900">영상 삭제 확인</h3>
            <p className="text-sm text-gray-600">
              이 영상과 연관된 분석·태그 데이터가 삭제됩니다. 계속하시겠습니까?
            </p>
            <p className="text-sm font-medium text-gray-800 line-clamp-3">{video.title}</p>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setDeleteConfirm(false)}
                disabled={deleting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? '삭제 중...' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
