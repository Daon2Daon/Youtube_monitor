import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runtimeApi } from '../../api/settings'
import type { RuntimeSettingsResponse, RuntimeSettingsUpdate } from '../../api/settings'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

function SecretInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm pr-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600">
        {show ? '숨김' : '표시'}
      </button>
    </div>
  )
}

function SliderField({ label, value, onChange, min, max, step = 1, format }: {
  label: string; value: number; onChange: (v: number) => void;
  min: number; max: number; step?: number; format?: (v: number) => string
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <span className="text-sm font-semibold text-blue-600 w-16 text-right">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-blue-600"
      />
      <div className="flex justify-between text-xs text-gray-400 mt-0.5">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  )
}

export default function RuntimeSettings() {
  const [data, setData] = useState<RuntimeSettingsResponse | null>(null)
  const [form, setForm] = useState<RuntimeSettingsUpdate & { youtube_api_key: string }>({
    youtube_api_key: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await runtimeApi.get()
      setData(d)
      setForm({
        master_interval_min: d.master_interval_min,
        pending_analysis_interval_min: d.pending_analysis_interval_min,
        default_channel_interval_min: d.default_channel_interval_min,
        youtube_api_key: '',
        youtube_daily_quota: d.youtube_daily_quota,
        window_days: d.window_days,
        max_concurrent_channels: d.max_concurrent_channels,
        max_concurrent_analyses: d.max_concurrent_analyses,
        analysis_interval_sec: d.analysis_interval_sec,
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      const { youtube_api_key, ...rest } = form
      const payload: RuntimeSettingsUpdate = {
        master_interval_min: rest.master_interval_min,
        pending_analysis_interval_min: rest.pending_analysis_interval_min,
        default_channel_interval_min: rest.default_channel_interval_min,
        youtube_daily_quota: rest.youtube_daily_quota,
        window_days: rest.window_days,
        max_concurrent_channels: rest.max_concurrent_channels,
        max_concurrent_analyses: rest.max_concurrent_analyses,
        analysis_interval_sec: rest.analysis_interval_sec,
      }
      if (youtube_api_key) payload.youtube_api_key = youtube_api_key
      const updated = await runtimeApi.update(payload)
      setData(updated)
      setSaved(true)
      setSaveMessage('저장되었습니다. 채널 모니터링·AI 배치 분석 스케줄이 즉시 반영됩니다.')
      setTimeout(() => setSaved(false), 4000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const setF = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">모니터링</h1>
      <p className="text-sm text-gray-500">
        채널 모니터링과 AI 배치 분석을 나누어 설정합니다. Telegram 알림·즉시/예약 발송은{' '}
        <Link to="/settings/notification" className="text-blue-600 hover:underline font-medium">
          알림 발송
        </Link>
        메뉴에서 설정하세요.
      </p>

      <form onSubmit={handleSave} className="space-y-5">
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">YouTube API</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                YouTube API Key
                {data?.youtube_api_key_masked && (
                  <span className="ml-2 text-xs text-gray-400 font-normal">현재: {data.youtube_api_key_masked}</span>
                )}
              </label>
              <SecretInput
                value={form.youtube_api_key ?? ''}
                onChange={(v) => setF('youtube_api_key', v)}
                placeholder="변경 시에만 입력"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">일일 쿼터 한도</label>
              <input
                type="number" min={100} max={1000000} step={100}
                value={form.youtube_daily_quota ?? 10000}
                onChange={(e) => setF('youtube_daily_quota', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* 하위: 채널 모니터링 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <div className="border-b pb-2">
            <h2 className="font-semibold text-gray-800">채널 모니터링</h2>
            <p className="text-xs text-gray-500 mt-1">
              전체 모니터링 주기마다 &quot;조회 시각이 된&quot; 채널만 YouTube에서 확인하여 신규 영상을 DB에 등록합니다.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                전체 모니터링 주기 (분)
              </label>
              <input
                type="number" min={1} max={10080}
                value={form.master_interval_min ?? 12}
                onChange={(e) => setF('master_interval_min', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">채널 목록을 훑어 &quot;지금 조회할 채널&quot;을 고르는 주기 (최대 7일=10080분)</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                채널별 모니터링 주기 (분)
              </label>
              <input
                type="number" min={10} max={10080}
                value={form.default_channel_interval_min ?? 720}
                onChange={(e) => setF('default_channel_interval_min', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">채널 목록에 개별 주기가 없을 때 적용되는 기본값. 해당 채널을 다시 YouTube에서 조회하기까지의 최소 간격</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                신규 영상 탐색 윈도우 (일)
              </label>
              <input
                type="number" min={1} max={3650}
                value={form.window_days ?? 1}
                onChange={(e) => setF('window_days', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                채널 폴링 시 이 기간(일) 이내 업로드된 영상을 모두 조회합니다. (최대 약 10년)
              </p>
            </div>
            <div className="md:col-span-2">
              <SliderField
                label="채널 동시성 (한 번의 전체 모니터링 실행 안에서)"
                value={form.max_concurrent_channels ?? 5}
                onChange={(v) => setF('max_concurrent_channels', v)}
                min={1} max={10}
                format={(v) => `${v}개`}
              />
            </div>
          </div>
        </div>

        {/* 하위: AI 배치 분석 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <div className="border-b pb-2">
            <h2 className="font-semibold text-gray-800">AI 배치 분석</h2>
            <p className="text-xs text-gray-500 mt-1">
              설정한 <strong>시간 간격(분)</strong>마다 백엔드 스케줄이 실행되며, 실행마다 DB의 미분석(pending) 영상 <strong>1건</strong>만
              선정하여 AI 분석 및 결과 DB 반영을 수행합니다. 긴 분석이 겹치지 않도록 동시 스케줄 인스턴스는 1개로 제한됩니다.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                AI 배치 분석 주기 (분)
              </label>
              <input
                type="number" min={1} max={10080}
                value={form.pending_analysis_interval_min ?? 12}
                onChange={(e) => setF('pending_analysis_interval_min', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                DB에만 쌓인 pending 영상을 처리하는 스케줄 주기입니다. 미설정 시 서버는 전체 모니터링 주기와 동일하게 쓸 수 있습니다(저장값 기준).
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                분석 간 추가 대기 (초)
              </label>
              <input
                type="number" min={0} max={3600} step={1}
                value={form.analysis_interval_sec ?? 120}
                onChange={(e) => setF('analysis_interval_sec', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                한 스케줄 실행에서 여러 건을 처리할 때 이전 호환용입니다. 현재 스케줄은 <strong>매회 1건</strong>만 처리하므로 보통은 영향이 작습니다. 0이면 대기 없음.
              </p>
            </div>
            <div className="md:col-span-2">
              <SliderField
                label="분석 동시성 (설정값 보존)"
                value={form.max_concurrent_analyses ?? 3}
                onChange={(v) => setF('max_concurrent_analyses', v)}
                min={1} max={10}
                format={(v) => `${v}개`}
              />
              <p className="text-xs text-gray-400 mt-1">
                스케줄 기반 미분석 처리는 현재 구현에서 매 실행당 1건·세마포어 1로 고정됩니다. 이 슬라이더는 향후 확장이나 다른 코드 경로와의 호환을 위해 유지됩니다.
              </p>
            </div>
          </div>
        </div>

        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
            ✅ {saveMessage}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </form>
    </div>
  )
}
