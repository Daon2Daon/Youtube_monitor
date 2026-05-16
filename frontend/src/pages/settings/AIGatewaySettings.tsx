import { useEffect, useState } from 'react'
import { aiGatewayApi } from '../../api/settings'
import type { AIGatewaySettingsResponse, AIGatewaySettingsUpdate, AIGatewayTestRequest, ModelInfo } from '../../api/settings'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

type TestState = { status: 'idle' | 'running' | 'ok' | 'fail'; message: string; latency?: number }
type AnalyzeState = { status: 'idle' | 'running' | 'ok' | 'fail'; message: string; model?: string }

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
      <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs">
        {show ? '숨김' : '표시'}
      </button>
    </div>
  )
}

function ModelSelect({ value, onChange, models, label }: {
  value: string; onChange: (v: string) => void; models: ModelInfo[]; label: string
}) {
  const [custom, setCustom] = useState(!models.find((m) => m.model_id === value) && value !== '')
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {models.length > 0 && !custom ? (
        <div className="flex gap-2">
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {models.map((m) => <option key={m.model_id} value={m.model_id}>{m.model_id}</option>)}
          </select>
          <button type="button" onClick={() => setCustom(true)} className="text-xs text-blue-600 whitespace-nowrap hover:underline">직접 입력</button>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="provider/model-name"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {models.length > 0 && (
            <button type="button" onClick={() => setCustom(false)} className="text-xs text-gray-500 whitespace-nowrap hover:underline">드롭다운</button>
          )}
        </div>
      )}
    </div>
  )
}

export default function AIGatewaySettings() {
  const [data, setData] = useState<AIGatewaySettingsResponse | null>(null)
  const [form, setForm] = useState<AIGatewaySettingsUpdate>({})
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [test, setTest] = useState<TestState>({ status: 'idle', message: '' })
  const [analyze, setAnalyze] = useState<AnalyzeState>({ status: 'idle', message: '' })
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await aiGatewayApi.get()
      setData(d)
      setForm({
        base_url: d.base_url,
        api_key: '',
        primary_model: d.primary_model,
        fallback_model: d.fallback_model,
        tagging_model: d.tagging_model,
        temperature: d.temperature,
        max_tokens: d.max_tokens,
        daily_budget_usd: d.daily_budget_usd,
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
      const payload = { ...form }
      if (!payload.api_key) delete payload.api_key
      const updated = await aiGatewayApi.update(payload)
      setData(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  /** 폼 현재값을 테스트 요청에 포함시킨다 (저장 전에도 동작). */
  const buildTestPayload = (): AIGatewayTestRequest => ({
    base_url: form.base_url || undefined,
    api_key: form.api_key || undefined,
    primary_model: form.primary_model || undefined,
  })

  const handleTest = async () => {
    setTest({ status: 'running', message: '연결 테스트 중...' })
    try {
      const r = await aiGatewayApi.testConnection(buildTestPayload())
      setTest({ status: r.success ? 'ok' : 'fail', message: r.message, latency: r.latency_ms })
      if (r.success) {
        const ms = await aiGatewayApi.listModels()
        setModels(ms.models)
      }
    } catch (e) {
      setTest({ status: 'fail', message: (e as Error).message })
    }
  }

  const handleTestAnalyze = async () => {
    setAnalyze({ status: 'running', message: '샘플 분석 실행 중...' })
    setShowAnalyzeModal(true)
    try {
      const r = await aiGatewayApi.testAnalyze(buildTestPayload())
      setAnalyze({ status: r.success ? 'ok' : 'fail', message: r.message, model: r.model_used })
    } catch (e) {
      setAnalyze({ status: 'fail', message: (e as Error).message })
    }
  }

  const setF = <K extends keyof AIGatewaySettingsUpdate>(k: K, v: AIGatewaySettingsUpdate[K]) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">AI Gateway</h1>
      <p className="text-sm text-gray-500">litellm Gateway 주소, API 키, 사용 모델을 설정합니다.</p>

      {/* 연결 테스트 결과 */}
      {test.status === 'ok' && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm flex gap-2">
          <span>🟢</span><span>{test.message}{test.latency != null && ` (${test.latency}ms)`}</span>
        </div>
      )}
      {test.status === 'fail' && (
        <div className="rounded-lg bg-red-50 border border-red-300 px-4 py-3 text-red-700 text-sm flex gap-2">
          <span>🔴</span><span>{test.message}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="bg-white rounded-xl shadow-sm p-6 space-y-5">
        {/* 연결 정보 */}
        <h2 className="font-semibold text-gray-800 border-b pb-2">연결 정보</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
            <input
              type="url"
              value={form.base_url ?? ''}
              onChange={(e) => setF('base_url', e.target.value)}
              placeholder="http://litellm:4000"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API Key
              {data?.api_key_masked && (
                <span className="ml-2 text-xs text-gray-400 font-normal">현재: {data.api_key_masked}</span>
              )}
            </label>
            <SecretInput
              value={form.api_key ?? ''}
              onChange={(v) => setF('api_key', v)}
              placeholder="변경 시에만 입력"
            />
          </div>
        </div>

        {/* 모델 설정 */}
        <h2 className="font-semibold text-gray-800 border-b pb-2 pt-2">모델 설정</h2>
        {models.length > 0 && (
          <p className="text-xs text-gray-500">연결 테스트 후 {models.length}개 모델을 불러왔습니다.</p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <ModelSelect
            label="Primary 모델 (영상 분석)"
            value={form.primary_model ?? ''}
            onChange={(v) => setF('primary_model', v)}
            models={models}
          />
          <ModelSelect
            label="Fallback 모델"
            value={form.fallback_model ?? ''}
            onChange={(v) => setF('fallback_model', v)}
            models={models}
          />
          <ModelSelect
            label="Tagging 모델"
            value={form.tagging_model ?? ''}
            onChange={(v) => setF('tagging_model', v)}
            models={models}
          />
        </div>

        {/* 세부 파라미터 */}
        <h2 className="font-semibold text-gray-800 border-b pb-2 pt-2">파라미터</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Temperature <span className="text-gray-400 font-normal">({form.temperature})</span>
            </label>
            <input
              type="range" min={0} max={2} step={0.05}
              value={form.temperature ?? 0.3}
              onChange={(e) => setF('temperature', Number(e.target.value))}
              className="w-full accent-blue-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5"><span>0</span><span>2</span></div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
            <input
              type="number" min={256} max={32768} step={256}
              value={form.max_tokens ?? 8192}
              onChange={(e) => setF('max_tokens', Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">일일 예산 (USD)</label>
            <input
              type="number" min={0} step={0.5}
              value={form.daily_budget_usd ?? 2.0}
              onChange={(e) => setF('daily_budget_usd', Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">✅ 저장되었습니다.</div>
        )}

        {/* 버튼 그룹 */}
        <div className="flex flex-wrap gap-3 pt-2">
          <button type="button" onClick={handleTest} disabled={test.status === 'running'}
            className="px-4 py-2 border border-blue-300 text-blue-600 rounded-lg text-sm hover:bg-blue-50 disabled:opacity-60">
            {test.status === 'running' ? '테스트 중...' : '연결 테스트'}
          </button>
          <button type="button" onClick={handleTestAnalyze} disabled={analyze.status === 'running'}
            className="px-4 py-2 border border-purple-300 text-purple-600 rounded-lg text-sm hover:bg-purple-50 disabled:opacity-60">
            샘플 분석 테스트
          </button>
          <button type="submit" disabled={saving}
            className="ml-auto px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </form>

      {/* 샘플 분석 결과 모달 */}
      {showAnalyzeModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-lg w-full space-y-4">
            <h3 className="font-bold text-gray-900">샘플 분석 테스트 결과</h3>
            <div className={`rounded-lg px-4 py-3 text-sm ${analyze.status === 'ok' ? 'bg-green-50 text-green-700' : analyze.status === 'fail' ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-600'}`}>
              {analyze.status === 'running' && '⏳ '}
              {analyze.status === 'ok' && '✅ '}
              {analyze.status === 'fail' && '❌ '}
              {analyze.message}
              {analyze.model && <p className="mt-1 text-xs text-gray-500">모델: {analyze.model}</p>}
            </div>
            <div className="flex justify-end">
              <button onClick={() => { setShowAnalyzeModal(false); setAnalyze({ status: 'idle', message: '' }) }}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
