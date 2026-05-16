/** YouTube Monitor API 클라이언트 */

const BASE = '/api/youtube'

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
  if (resp.status === 204) return undefined as T
  return resp.json()
}

// ── 타입 ─────────────────────────────────────────────────────────────────────

export interface Channel {
  channel_pk: number
  channel_id: string
  channel_name: string
  channel_handle: string | null
  thumbnail_url: string | null
  description: string | null
  category: string | null
  poll_interval_min: number
  is_active: boolean
  notify_enabled: boolean
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface VideoSummary {
  one_line: string
  headline: string | null
}

export interface Video {
  video_pk: number
  channel_pk: number
  video_id: string
  video_url: string
  title: string
  thumbnail_url: string | null
  published_at: string
  duration_seconds: number | null
  view_count: number | null
  like_count: number | null
  analysis_status: 'pending' | 'processing' | 'done' | 'failed'
  notified_at: string | null
  created_at: string
  summary: VideoSummary | null
  source_channel_name: string | null
}

export interface VideoDetail extends Video {
  description: string | null
  sequence_in_channel: number | null
  analysis_error: string | null
  retry_count: number
  updated_at: string
  one_line: string | null
  headline: string | null
  short_summary_md: string | null
  full_analysis_md: string | null
  bullet_points: string[] | null
  key_points: unknown[] | null
  insights: unknown[] | null
  entities: Record<string, unknown> | null
  sentiment: string | null
  confidence_score: number | null
  model_name: string | null
  analyzed_at: string | null
  tags: string[]
}

export interface InstantAnalyzeResponse {
  video_pk: number
  video_id: string
  title: string
  source_channel_name: string
  analysis_status: string
  existing: boolean
  message: string
}

export interface PaginatedVideos {
  total: number
  page: number
  page_size: number
  items: Video[]
}

export interface Tag {
  tag_pk: number
  name: string
  tag_type: string
  video_count: number
}

export interface JobLog {
  log_pk: number
  job_type: string
  channel_pk: number | null
  video_pk: number | null
  status: string
  message: string | null
  duration_ms: number | null
  started_at: string
}

export interface PaginatedJobLogs {
  total: number
  page: number
  page_size: number
  items: JobLog[]
}

export interface Stats {
  total_channels: number
  active_channels: number
  total_videos: number
  analyzed_videos: number
  pending_videos: number
  failed_videos: number
  notified_videos: number
  total_tags: number
  last_poll_at: string | null
}

export interface DBHealthResponse {
  healthy: boolean
  message: string
  latency_ms: number | null
}

export interface PollTriggerResponse {
  job_id: string
  message: string
}

export interface PromptSettings {
  analysis_prompt: string
  prompt_version: string
}

// ── 채널 API ─────────────────────────────────────────────────────────────────

export const channelApi = {
  list: (isActive?: boolean) =>
    request<Channel[]>(`/channels${isActive !== undefined ? `?is_active=${isActive}` : ''}`),

  add: (body: {
    channel_input: string
    category?: string
    poll_interval_min?: number
    notify_enabled?: boolean
    auto_poll_now?: boolean
  }) => request<Channel>('/channels', { method: 'POST', body: JSON.stringify(body) }),

  update: (pk: number, body: Partial<Pick<Channel, 'is_active' | 'notify_enabled' | 'poll_interval_min' | 'category'>>) =>
    request<Channel>(`/channels/${pk}`, { method: 'PATCH', body: JSON.stringify(body) }),

  remove: (pk: number) => request<void>(`/channels/${pk}`, { method: 'DELETE' }),

  poll: (pk: number) =>
    request<PollTriggerResponse>(`/channels/${pk}/poll`, { method: 'POST' }),
}

// ── 영상 API ─────────────────────────────────────────────────────────────────

export const videoApi = {
  list: (params: {
    channel_pk?: number
    tag?: string
    analysis_status?: string
    since?: string
    page?: number
    page_size?: number
  }) => {
    const q = new URLSearchParams()
    if (params.channel_pk != null) q.set('channel_pk', String(params.channel_pk))
    if (params.tag) q.set('tag', params.tag)
    if (params.analysis_status) q.set('analysis_status', params.analysis_status)
    if (params.since) q.set('since', params.since)
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    return request<PaginatedVideos>(`/videos?${q}`)
  },

  get: (pk: number) => request<VideoDetail>(`/videos/${pk}`),

  reanalyze: (pk: number, customPrompt?: string) =>
    request<PollTriggerResponse>(`/videos/${pk}/reanalyze`, {
      method: 'POST',
      body: JSON.stringify({ custom_prompt: customPrompt ?? null }),
    }),

  remove: (pk: number) => request<void>(`/videos/${pk}`, { method: 'DELETE' }),

  notify: (pk: number, force = false) =>
    request<VideoNotifyResponse>(`/videos/${pk}/notify`, {
      method: 'POST',
      body: JSON.stringify({ force }),
    }),
}

export interface VideoNotifyResponse {
  success: boolean
  message: string
  notified_at: string | null
}

// ── 태그 API ─────────────────────────────────────────────────────────────────

export const tagApi = {
  list: (minCount = 1, limit = 100) =>
    request<Tag[]>(`/tags?min_count=${minCount}&limit=${limit}`),
}

// ── 통계 API ─────────────────────────────────────────────────────────────────

export const statsApi = {
  get: () => request<Stats>('/stats'),
}

// ── 잡 로그 API ───────────────────────────────────────────────────────────────

export const jobApi = {
  list: (params: {
    job_type?: string
    status?: string
    channel_pk?: number
    page?: number
    page_size?: number
  }) => {
    const q = new URLSearchParams()
    if (params.job_type) q.set('job_type', params.job_type)
    if (params.status) q.set('status', params.status)
    if (params.channel_pk != null) q.set('channel_pk', String(params.channel_pk))
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    return request<PaginatedJobLogs>(`/jobs/logs?${q}`)
  },
}

// ── 프롬프트 설정 API ─────────────────────────────────────────────────────────

export const promptApi = {
  get: () => request<PromptSettings>('/settings/prompts'),

  update: (body: Partial<Pick<PromptSettings, 'analysis_prompt'>>) =>
    request<PromptSettings>('/settings/prompts', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  reset: () =>
    request<PromptSettings>('/settings/prompts/reset', { method: 'DELETE' }),
}

// ── 즉시(추가 영상) 분석 API ──────────────────────────────────────────────────

export const instantApi = {
  analyze: (videoUrl: string, customPrompt?: string) =>
    request<InstantAnalyzeResponse>('/instant-analyze', {
      method: 'POST',
      body: JSON.stringify({ video_url: videoUrl, custom_prompt: customPrompt ?? null }),
    }),
}

// ── 헬스 API ─────────────────────────────────────────────────────────────────

export const healthApi = {
  dbHealth: () => request<DBHealthResponse>('/settings/database/health'),
  gatewayHealth: () => request<{ success: boolean; message: string; latency_ms?: number }>('/settings/ai_gateway/test_connection', { method: 'POST' }),
}
