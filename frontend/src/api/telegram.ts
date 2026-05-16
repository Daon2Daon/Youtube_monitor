/** Telegram Chat ID 연동 API (/auth/telegram/*) */

const AUTH_BASE = '/auth'

async function parseError(resp: Response): Promise<string> {
  try {
    const body = await resp.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join(', ')
  } catch {
    /* ignore */
  }
  return resp.statusText || '요청 실패'
}

export interface TelegramStatus {
  telegram_connected: boolean
  chat_id: string | null
  bot_token_configured: boolean
}

export const telegramApi = {
  status: async (): Promise<TelegramStatus> => {
    const resp = await fetch(`${AUTH_BASE}/telegram/status`, { credentials: 'include' })
    if (!resp.ok) throw new Error(await parseError(resp))
    return resp.json()
  },

  configure: async (chatId: string): Promise<{ message: string; chat_id: string }> => {
    const form = new FormData()
    form.append('chat_id', chatId.trim())
    const resp = await fetch(`${AUTH_BASE}/telegram/configure`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
    if (!resp.ok) throw new Error(await parseError(resp))
    return resp.json()
  },

  test: async (): Promise<{ message: string; chat_id: string }> => {
    const resp = await fetch(`${AUTH_BASE}/telegram/test`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!resp.ok) throw new Error(await parseError(resp))
    return resp.json()
  },
}
