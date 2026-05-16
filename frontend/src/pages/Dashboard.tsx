import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import dayjs from 'dayjs'
import { statsApi, healthApi, videoApi } from '../api/client'
import { runtimeApi } from '../api/settings'
import type { Stats, DBHealthResponse, Video } from '../api/client'
import Spinner from '../components/Spinner'
import ErrorBanner from '../components/ErrorBanner'
import StatusBadge from '../components/StatusBadge'
function StatCard({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-5 flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      <span className={`text-3xl font-bold ${color ?? 'text-gray-900'}`}>{value}</span>
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [health, setHealth] = useState<DBHealthResponse | null>(null)
  const [gatewayOk, setGatewayOk] = useState<boolean | null>(null)
  const [gatewayMsg, setGatewayMsg] = useState('')
  const [recentVideos, setRecentVideos] = useState<Video[]>([])
  const [windowDays, setWindowDays] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const runtime = await runtimeApi.get()
      const days = Math.max(1, runtime.window_days ?? 1)
      setWindowDays(days)
      const since = dayjs().subtract(days, 'day').toISOString()
      const [s, h, v, gw] = await Promise.allSettled([
        statsApi.get(),
        healthApi.dbHealth(),
        videoApi.list({ since, page_size: 12, page: 1 }),
        healthApi.gatewayHealth(),
      ])
      if (s.status === 'fulfilled') setStats(s.value)
      if (h.status === 'fulfilled') setHealth(h.value)
      if (v.status === 'fulfilled') setRecentVideos(v.value.items)
      if (gw.status === 'fulfilled') {
        setGatewayOk(gw.value.success)
        setGatewayMsg(gw.value.message)
      } else {
        setGatewayOk(false)
        setGatewayMsg('연결 확인 불가')
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>

      {/* 헬스 배너 그룹 */}
      <div className="space-y-2">
        {health && !health.healthy && (
          <div className="rounded-lg bg-red-50 border border-red-300 px-4 py-3 text-red-700 text-sm flex items-center gap-2">
            <span className="font-semibold">DB 오류</span>
            <span>{health.message} (DATABASE_URL·data/ 디렉터리 확인)</span>
          </div>
        )}
        {health?.healthy && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm flex items-center gap-2">
            <span className="font-semibold">DB 정상</span>
            <span>{health.latency_ms != null && `응답 ${health.latency_ms}ms`}</span>
          </div>
        )}
        {gatewayOk === false && (
          <div className="rounded-lg bg-orange-50 border border-orange-300 px-4 py-3 text-orange-700 text-sm flex items-center gap-2">
            <span className="font-semibold">AI Gateway 오류</span>
            <span>{gatewayMsg}</span>
            <Link to="/settings/ai-gateway" className="ml-auto underline">설정으로 이동</Link>
          </div>
        )}
        {gatewayOk === true && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm flex items-center gap-2">
            <span className="font-semibold">AI Gateway 정상</span>
            <span>{gatewayMsg}</span>
          </div>
        )}
      </div>

      {/* 통계 카드 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="전체 채널" value={stats.total_channels} />
          <StatCard label="활성 채널" value={stats.active_channels} color="text-blue-600" />
          <StatCard label="전체 영상" value={stats.total_videos} />
          <StatCard label="분석 완료" value={stats.analyzed_videos} color="text-green-600" />
          <StatCard label="분석 대기" value={stats.pending_videos} color="text-yellow-600" />
          <StatCard label="분석 실패" value={stats.failed_videos} color="text-red-600" />
          <StatCard label="알림 발송" value={stats.notified_videos} />
          <StatCard label="전체 태그" value={stats.total_tags} />
        </div>
      )}

      {/* 최근 24시간 영상 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-800">최근 {windowDays}일 신규 영상</h2>
          <Link to="/videos" className="text-blue-600 text-sm hover:underline">전체 보기 →</Link>
        </div>
        {recentVideos.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-8">최근 {windowDays}일 내 신규 영상이 없습니다.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {recentVideos.map((v) => (
              <Link
                key={v.video_pk}
                to={`/videos/${v.video_pk}`}
                className="bg-white rounded-xl shadow-sm overflow-hidden hover:shadow-md transition-shadow"
              >
                {v.thumbnail_url ? (
                  <img src={v.thumbnail_url} alt={v.title} className="w-full aspect-video object-cover" />
                ) : (
                  <div className="w-full aspect-video bg-gray-100 flex items-center justify-center text-gray-400 text-4xl">🎬</div>
                )}
                <div className="p-3 space-y-1.5">
                  <p className="text-sm font-medium text-gray-900 line-clamp-2">{v.title}</p>
                  {v.summary?.one_line && (
                    <p className="text-xs text-gray-500 line-clamp-1">{v.summary.one_line}</p>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <StatusBadge status={v.analysis_status} />
                    <span className="text-xs text-gray-400">{dayjs(v.published_at).format('MM/DD HH:mm')}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
