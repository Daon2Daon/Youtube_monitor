/** YouTube Monitor 설정 API 클라이언트 */

const BASE = '/api/youtube/settings'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(detail?.detail ?? resp.statusText)
  }
  return resp.json()
}

// ── 타입 ─────────────────────────────────────────────────────────────────────

export interface AIGatewaySettingsResponse {
  base_url: string
  api_key_masked: string
  primary_model: string
  fallback_model: string
  tagging_model: string
  temperature: number
  max_tokens: number
  daily_budget_usd: number
}

export interface AIGatewaySettingsUpdate {
  base_url?: string
  api_key?: string
  primary_model?: string
  fallback_model?: string
  tagging_model?: string
  temperature?: number
  max_tokens?: number
  daily_budget_usd?: number
}

export interface ModelInfo {
  model_id: string
  provider?: string
}

export interface RuntimeSettingsResponse {
  master_interval_min: number
  pending_analysis_interval_min: number
  default_channel_interval_min: number
  youtube_api_key_masked: string
  youtube_daily_quota: number
  window_days: number
  max_concurrent_channels: number
  max_concurrent_analyses: number
  analysis_interval_sec: number
  telegram_enabled: boolean
  wait_between_messages_sec: number
  low_confidence_threshold: number
}

export interface RuntimeSettingsUpdate {
  master_interval_min?: number
  pending_analysis_interval_min?: number
  default_channel_interval_min?: number
  youtube_api_key?: string
  youtube_daily_quota?: number
  window_days?: number
  max_concurrent_channels?: number
  max_concurrent_analyses?: number
  analysis_interval_sec?: number
  telegram_enabled?: boolean
  wait_between_messages_sec?: number
  low_confidence_threshold?: number
}

export interface ConnectionTestResponse {
  success: boolean
  message: string
  latency_ms?: number
}

export interface GatewayTestAnalyzeResponse {
  success: boolean
  message: string
  model_used?: string
  latency_ms?: number
}

/** 저장 전 폼 현재값으로 테스트할 때 함께 전달하는 바디. */
export interface AIGatewayTestRequest {
  base_url?: string
  api_key?: string
  primary_model?: string
}

// ── AI Gateway 설정 API ───────────────────────────────────────────────────────

export const aiGatewayApi = {
  get: () => request<AIGatewaySettingsResponse>('/ai_gateway'),
  update: (body: AIGatewaySettingsUpdate) =>
    request<AIGatewaySettingsResponse>('/ai_gateway', { method: 'PUT', body: JSON.stringify(body) }),
  /** 폼 현재값을 넘기면 저장 없이 해당 값으로 테스트한다. */
  testConnection: (formValues?: AIGatewayTestRequest) =>
    request<ConnectionTestResponse>('/ai_gateway/test_connection', {
      method: 'POST',
      body: JSON.stringify(formValues ?? {}),
    }),
  /** 폼 현재값을 넘기면 저장 없이 해당 값으로 분석 테스트한다. */
  testAnalyze: (formValues?: AIGatewayTestRequest) =>
    request<GatewayTestAnalyzeResponse>('/ai_gateway/test_analyze', {
      method: 'POST',
      body: JSON.stringify(formValues ?? {}),
    }),
  listModels: () =>
    request<{ models: ModelInfo[] }>('/ai_gateway/models'),
}

// ── 런타임 설정 API ───────────────────────────────────────────────────────────

export const runtimeApi = {
  get: () => request<RuntimeSettingsResponse>('/runtime'),
  update: (body: RuntimeSettingsUpdate) =>
    request<RuntimeSettingsResponse>('/runtime', { method: 'PUT', body: JSON.stringify(body) }),
}
