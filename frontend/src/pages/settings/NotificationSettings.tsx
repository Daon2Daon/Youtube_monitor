import { useEffect, useState, useRef } from 'react'
import { notificationApi } from '../../api/notification'
import type { NotificationSettingsResponse, NotificationSettingsUpdate, SendMode } from '../../api/notification'
import { telegramApi, type TelegramStatus } from '../../api/telegram'
import Spinner from '../../components/Spinner'
import ErrorBanner from '../../components/ErrorBanner'

// ── 작은 UI 컴포넌트 ────────────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  description?: string
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`mt-0.5 relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-blue-600' : 'bg-gray-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
      <div>
        <span className="text-sm text-gray-700 font-medium">{label}</span>
        {description && <p className="text-xs text-gray-400 mt-0.5">{description}</p>}
      </div>
    </label>
  )
}

/** HH:MM 형식 검증 */
function isValidTime(t: string): boolean {
  return /^([01]?\d|2[0-3]):[0-5]\d$/.test(t)
}

/** HH:MM → 표시용 "HH:MM" 정렬 */
function sortTimes(times: string[]): string[] {
  return [...times].sort((a, b) => {
    const toMin = (t: string) => {
      const [h, m] = t.split(':').map(Number)
      return h * 60 + m
    }
    return toMin(a) - toMin(b)
  })
}

// ── 예약 시간 목록 편집기 ────────────────────────────────────────────────────

function ScheduledTimeEditor({
  times,
  onChange,
}: {
  times: string[]
  onChange: (v: string[]) => void
}) {
  const [input, setInput] = useState('')
  const [inputError, setInputError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleAdd = () => {
    const trimmed = input.trim()
    if (!trimmed) return
    if (!isValidTime(trimmed)) {
      setInputError('HH:MM 형식(24시간제)으로 입력하세요. 예: 14:00')
      return
    }
    if (times.includes(trimmed)) {
      setInputError('이미 등록된 시각입니다.')
      return
    }
    if (times.length >= 10) {
      setInputError('최대 10개까지 등록할 수 있습니다.')
      return
    }
    onChange(sortTimes([...times, trimmed]))
    setInput('')
    setInputError('')
    inputRef.current?.focus()
  }

  const handleRemove = (t: string) => {
    onChange(times.filter((x) => x !== t))
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAdd()
    }
  }

  return (
    <div className="space-y-3">
      {/* 등록된 시각 목록 */}
      {times.length === 0 ? (
        <p className="text-sm text-gray-400 italic">등록된 예약 시각이 없습니다.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {times.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-50 border border-blue-200 rounded-full text-sm font-medium text-blue-700"
            >
              {t}
              <button
                type="button"
                onClick={() => handleRemove(t)}
                className="text-blue-400 hover:text-red-500 transition-colors leading-none"
                aria-label={`${t} 삭제`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 시각 추가 입력 */}
      <div className="flex gap-2 items-start">
        <div className="flex-1">
          <input
            ref={inputRef}
            type="time"
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              setInputError('')
            }}
            onKeyDown={handleKeyDown}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {inputError && (
            <p className="text-xs text-red-500 mt-1">{inputError}</p>
          )}
        </div>
        <button
          type="button"
          onClick={handleAdd}
          disabled={times.length >= 10}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
        >
          추가
        </button>
      </div>
      <p className="text-xs text-gray-400">
        매일 지정한 시각마다 미발송 영상 분석 결과를 순차 발송합니다. 시각은 최대 10개까지 등록할 수 있으며,
        한 시각(한 회차)당 발송 건수는 아래 &quot;예약발송 회당 최대 건수&quot;로 제한됩니다.
      </p>
    </div>
  )
}

// ── Telegram Chat ID 연동 ───────────────────────────────────────────────────

function TelegramChatIdSection({
  status,
  onStatusChange,
}: {
  status: TelegramStatus | null
  onStatusChange: (s: TelegramStatus) => void
}) {
  const [chatIdDraft, setChatIdDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  useEffect(() => {
    setChatIdDraft(status?.chat_id ?? '')
  }, [status?.chat_id])

  const handleSaveChatId = async () => {
    const trimmed = chatIdDraft.trim()
    if (!trimmed) {
      setMsg({ type: 'err', text: 'Chat ID를 입력해 주세요.' })
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      const res = await telegramApi.configure(trimmed)
      onStatusChange({
        telegram_connected: true,
        chat_id: res.chat_id,
        bot_token_configured: status?.bot_token_configured ?? false,
      })
      setMsg({ type: 'ok', text: res.message })
    } catch (e) {
      setMsg({ type: 'err', text: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setMsg(null)
    try {
      const res = await telegramApi.test()
      setMsg({ type: 'ok', text: res.message })
    } catch (e) {
      setMsg({ type: 'err', text: (e as Error).message })
    } finally {
      setTesting(false)
    }
  }

  const botOk = status?.bot_token_configured ?? false
  const chatOk = status?.telegram_connected ?? false

  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-3 bg-gray-50/80">
      <div>
        <h3 className="text-sm font-semibold text-gray-800">Telegram 수신 Chat ID</h3>
        <p className="text-xs text-gray-500 mt-1">
          봇 토큰은 서버 환경변수 <code className="bg-gray-200 px-1 rounded">TELEGRAM_BOT_TOKEN</code>에서 읽습니다.
          수신 대상 Chat ID만 여기서 등록합니다.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <span
          className={`px-2 py-1 rounded-full border ${
            botOk ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          봇 토큰: {botOk ? '설정됨' : '미설정'}
        </span>
        <span
          className={`px-2 py-1 rounded-full border ${
            chatOk ? 'bg-green-50 border-green-200 text-green-700' : 'bg-amber-50 border-amber-200 text-amber-700'
          }`}
        >
          Chat ID: {chatOk ? '등록됨' : '미등록'}
        </span>
      </div>

      {!botOk && (
        <p className="text-xs text-red-600">
          Docker <code className="bg-red-100 px-1 rounded">.env</code>에 TELEGRAM_BOT_TOKEN을 설정한 뒤 컨테이너를 재시작하세요.
        </p>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={chatIdDraft}
          onChange={(e) => {
            setChatIdDraft(e.target.value)
            setMsg(null)
          }}
          placeholder="예: 123456789 또는 -1001234567890"
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          spellCheck={false}
        />
        <button
          type="button"
          onClick={handleSaveChatId}
          disabled={saving || testing}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap"
        >
          {saving ? '저장 중...' : 'Chat ID 저장'}
        </button>
        <button
          type="button"
          onClick={handleTest}
          disabled={saving || testing || !chatOk || !botOk}
          className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-white disabled:opacity-50 whitespace-nowrap"
        >
          {testing ? '발송 중...' : '테스트 발송'}
        </button>
      </div>

      <p className="text-xs text-gray-500">
        Chat ID 확인: Telegram에서 봇에게 <strong>/start</strong>를 보낸 뒤,
        @userinfobot 또는 @getidsbot 등으로 본인(또는 그룹) ID를 조회하세요.
      </p>

      {msg && (
        <p
          className={`text-xs px-3 py-2 rounded-lg border ${
            msg.type === 'ok'
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          {msg.text}
        </p>
      )}
    </div>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────────────────────

export default function NotificationSettings() {
  const [data, setData] = useState<NotificationSettingsResponse | null>(null)
  const [form, setForm] = useState<NotificationSettingsUpdate>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, tg] = await Promise.all([
        notificationApi.get(),
        telegramApi.status(),
      ])
      setTelegramStatus(tg)
      setData(d)
      setForm({
        telegram_enabled: d.telegram_enabled,
        send_mode: d.send_mode,
        scheduled_times: d.scheduled_times,
        scheduled_max_per_run: d.scheduled_max_per_run,
        wait_between_messages_sec: d.wait_between_messages_sec,
        low_confidence_threshold: d.low_confidence_threshold,
        quiet_hours_enabled: d.quiet_hours_enabled,
        quiet_hours_start: d.quiet_hours_start,
        quiet_hours_end: d.quiet_hours_end,
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const setF = <K extends keyof NotificationSettingsUpdate>(
    k: K,
    v: NotificationSettingsUpdate[K]
  ) => setForm((prev) => ({ ...prev, [k]: v }))

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      const updated = await notificationApi.update(form)
      setData(updated)
      setForm({
        telegram_enabled: updated.telegram_enabled,
        send_mode: updated.send_mode,
        scheduled_times: updated.scheduled_times,
        scheduled_max_per_run: updated.scheduled_max_per_run,
        wait_between_messages_sec: updated.wait_between_messages_sec,
        low_confidence_threshold: updated.low_confidence_threshold,
        quiet_hours_enabled: updated.quiet_hours_enabled,
        quiet_hours_start: updated.quiet_hours_start,
        quiet_hours_end: updated.quiet_hours_end,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 4000)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} onRetry={load} />

  const sendMode = form.send_mode ?? 'immediate'

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-gray-900">알림 발송</h1>
      <p className="text-sm text-gray-500">
        Telegram 발송 모드와 예약 일정을 설정합니다.
      </p>

      <form onSubmit={handleSave} className="space-y-5">

        {/* Telegram 기본 설정 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
          <h2 className="font-semibold text-gray-800 border-b pb-2">Telegram 기본 설정</h2>

          <ToggleSwitch
            checked={form.telegram_enabled ?? true}
            onChange={(v) => setF('telegram_enabled', v)}
            label="Telegram 알림 활성화"
            description="비활성화하면 즉시발송·예약발송 모두 중단됩니다."
          />

          <TelegramChatIdSection
            status={telegramStatus}
            onStatusChange={setTelegramStatus}
          />

          <div className="border border-gray-200 rounded-lg p-4 space-y-4 bg-gray-50/80">
            <ToggleSwitch
              checked={form.quiet_hours_enabled ?? false}
              onChange={(v) => setF('quiet_hours_enabled', v)}
              label="야간 알림 제한 (KST)"
              description="지정한 시간대에는 Telegram 발송을 하지 않습니다. 분석은 계속되며, 즉시발송 모드에서는 제한 종료 5분 후 자동 보정 발송됩니다."
            />
            {form.quiet_hours_enabled && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    제한 시작
                  </label>
                  <input
                    type="time"
                    value={form.quiet_hours_start ?? '22:00'}
                    onChange={(e) => setF('quiet_hours_start', e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    제한 종료
                  </label>
                  <input
                    type="time"
                    value={form.quiet_hours_end ?? '07:00'}
                    onChange={(e) => setF('quiet_hours_end', e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  />
                </div>
              </div>
            )}
            {form.quiet_hours_enabled && (
              <p className="text-xs text-gray-500">
                예: 22:00 ~ 07:00 → 밤 10시부터 다음 날 오전 7시 전까지 발송하지 않습니다.
                종료 시각이 시작보다 이르면 자정을 넘기는 구간으로 적용됩니다.
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                건별 발송 대기 시간 (초)
              </label>
              <input
                type="number"
                min={0}
                max={600}
                value={form.wait_between_messages_sec ?? 30}
                onChange={(e) => setF('wait_between_messages_sec', Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                예약발송 시 영상 사이 대기 시간 (Telegram 스팸 방지)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                저신뢰도 임계값 ({Math.round((form.low_confidence_threshold ?? 0.5) * 100)}%)
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={form.low_confidence_threshold ?? 0.5}
                onChange={(e) => setF('low_confidence_threshold', Number(e.target.value))}
                className="w-full accent-blue-600 mt-2"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0%</span>
                <span>100%</span>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                임계값 미만 분석 결과에 ⚠️ 저신뢰도 배지 표시
              </p>
            </div>
          </div>
        </div>

        {/* 발송 모드 선택 */}
        <div className="bg-white rounded-xl shadow-sm p-6 space-y-5">
          <h2 className="font-semibold text-gray-800 border-b pb-2">발송 모드</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* 즉시발송 카드 */}
            <button
              type="button"
              onClick={() => setF('send_mode', 'immediate')}
              className={`text-left p-4 rounded-xl border-2 transition-all ${
                sendMode === 'immediate'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">⚡</span>
                <span className="font-semibold text-gray-800 text-sm">즉시발송</span>
                {sendMode === 'immediate' && (
                  <span className="ml-auto text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
                    선택됨
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500">
                영상 분석이 완료되는 즉시 Telegram으로 발송합니다.
              </p>
            </button>

            {/* 예약발송 카드 */}
            <button
              type="button"
              onClick={() => setF('send_mode', 'scheduled')}
              className={`text-left p-4 rounded-xl border-2 transition-all ${
                sendMode === 'scheduled'
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-gray-300'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">🕐</span>
                <span className="font-semibold text-gray-800 text-sm">예약발송</span>
                {sendMode === 'scheduled' && (
                  <span className="ml-auto text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
                    선택됨
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500">
                지정한 일정에 맞춰 미발송 영상을 일괄 발송합니다.
              </p>
            </button>
          </div>
        </div>

        {/* 예약 시각 설정 (예약발송 모드일 때만 표시) */}
        {sendMode === 'scheduled' && (
          <div className="bg-white rounded-xl shadow-sm p-6 space-y-4">
            <h2 className="font-semibold text-gray-800 border-b pb-2">예약 발송</h2>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                예약발송 회당 최대 발송 건수
              </label>
              <input
                type="number"
                min={1}
                max={50}
                value={form.scheduled_max_per_run ?? 5}
                onChange={(e) => setF('scheduled_max_per_run', Number(e.target.value))}
                className="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                각 예약 시각이 실행될 때마다, 분석 완료·미발송 영상을 오래된 순으로 최대 이 개수만큼만 Telegram으로 보냅니다.
                더 남아 있으면 다음 예약 시각(또는 같은 시각의 다음 날 회차)에 이어서 발송합니다.
              </p>
            </div>
            <div className="border-t pt-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">예약 발송 시각</h3>
              <ScheduledTimeEditor
                times={form.scheduled_times ?? []}
                onChange={(v) => setF('scheduled_times', v)}
              />
            </div>
            {(form.scheduled_times ?? []).length === 0 && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-xs">
                예약발송 모드에서는 최소 1개 이상의 시각을 등록해야 실제 발송이 이루어집니다.
              </div>
            )}
          </div>
        )}

        {/* 저장 완료 메시지 */}
        {saved && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
            ✅ 저장되었습니다.
            {sendMode === 'scheduled'
              ? ' 예약발송 스케줄이 즉시 반영됩니다.'
              : ' 다음 분석부터 즉시발송이 적용됩니다.'}
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

      {/* 현재 설정 요약 */}
      {data && (
        <div className="bg-gray-50 rounded-xl border p-4 text-xs text-gray-500 space-y-1">
          <p className="font-medium text-gray-600 mb-2">현재 적용 중인 설정</p>
          <p>Telegram: {data.telegram_enabled ? '활성' : '비활성'}</p>
          <p>
            Chat ID: {telegramStatus?.telegram_connected
              ? (telegramStatus.chat_id ?? '(등록됨)')
              : '(미등록)'}
          </p>
          <p>봇 토큰(환경변수): {telegramStatus?.bot_token_configured ? '설정됨' : '미설정'}</p>
          <p>
            발송 모드: {data.send_mode === 'immediate' ? '즉시발송' : '예약발송'}
          </p>
          {data.send_mode === 'scheduled' && (
            <p>
              예약 시각: {data.scheduled_times.length > 0
                ? data.scheduled_times.join(', ')
                : '(없음)'}
            </p>
          )}
          {data.send_mode === 'scheduled' && (
            <p>예약발송 회당 최대: {data.scheduled_max_per_run}건</p>
          )}
          <p>건별 대기: {data.wait_between_messages_sec}초</p>
          <p>저신뢰도 임계값: {Math.round(data.low_confidence_threshold * 100)}%</p>
          <p>
            야간 제한: {data.quiet_hours_enabled
              ? `${data.quiet_hours_start} ~ ${data.quiet_hours_end} (KST)`
              : '비활성'}
          </p>
        </div>
      )}
    </div>
  )
}
