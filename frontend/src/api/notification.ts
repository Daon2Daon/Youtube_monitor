/** YouTube Monitor — 알림 발송 설정 API 클라이언트 */

const BASE = '/api/youtube/settings/notification'

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

export type SendMode = 'immediate' | 'scheduled'

export interface NotificationSettingsResponse {
  telegram_enabled: boolean
  /** 'immediate' | 'scheduled' */
  send_mode: SendMode
  /** 예약 시각 목록 ["HH:MM", ...] */
  scheduled_times: string[]
  /** 예약발송 한 회차당 최대 발송 건수 (잔여는 다음 회차) */
  scheduled_max_per_run: number
  wait_between_messages_sec: number
  low_confidence_threshold: number
  quiet_hours_enabled: boolean
  quiet_hours_start: string
  quiet_hours_end: string
}

export interface NotificationSettingsUpdate {
  telegram_enabled?: boolean
  send_mode?: SendMode
  scheduled_times?: string[]
  scheduled_max_per_run?: number
  wait_between_messages_sec?: number
  low_confidence_threshold?: number
  quiet_hours_enabled?: boolean
  quiet_hours_start?: string
  quiet_hours_end?: string
}

// ── API ───────────────────────────────────────────────────────────────────────

export const notificationApi = {
  get: () => request<NotificationSettingsResponse>(''),
  update: (body: NotificationSettingsUpdate) =>
    request<NotificationSettingsResponse>('', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
