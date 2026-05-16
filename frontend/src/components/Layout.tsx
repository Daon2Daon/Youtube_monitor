import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { healthApi } from '../api/client'

const MAIN_NAV = [
  { to: '/', label: '대시보드', icon: '🏠', end: true },
  { to: '/channels', label: '채널 관리', icon: '📺' },
  { to: '/videos', label: '영상 목록', icon: '🎬' },
  { to: '/instant-analyze', label: '영상 분석', icon: '🔍' },
  { to: '/tags', label: '태그 클라우드', icon: '🏷' },
  { to: '/jobs', label: 'Logs', icon: '📋' },
]

const SETTINGS_NAV = [
  { to: '/settings/ai-gateway', label: 'AI Gateway', icon: '🤖' },
  { to: '/settings/runtime', label: '모니터링', icon: '⚙️' },
  { to: '/settings/notification', label: '알림 발송', icon: '🔔' },
  { to: '/settings/prompts', label: '프롬프트', icon: '📝' },
]

type HealthState = 'unknown' | 'ok' | 'error'

export default function Layout() {
  const [dbHealth, setDbHealth] = useState<HealthState>('unknown')
  const [dbMsg, setDbMsg] = useState('')
  const location = useLocation()
  const isOnSettings = location.pathname.includes('/settings')
  const [settingsOpen, setSettingsOpen] = useState(isOnSettings)

  useEffect(() => {
    if (isOnSettings) setSettingsOpen(true)
  }, [isOnSettings])

  const checkHealth = async () => {
    try {
      const res = await healthApi.dbHealth()
      setDbHealth(res.healthy ? 'ok' : 'error')
      setDbMsg(res.message)
    } catch {
      setDbHealth('error')
      setDbMsg('DB 연결 확인 불가')
    }
  }

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 60_000)
    return () => clearInterval(id)
  }, [])

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex shrink-0 items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors whitespace-nowrap lg:whitespace-normal ${
      isActive ? 'bg-blue-600 text-white font-medium' : 'text-gray-700 hover:bg-gray-100'
    }`

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {dbHealth === 'error' && (
        <div className="bg-red-600 text-white text-sm px-4 py-2 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <span>SQLite 연결 오류: {dbMsg} (.env의 DATABASE_URL 및 data/ 볼륨을 확인하세요)</span>
        </div>
      )}

      <div className="flex flex-col lg:flex-row flex-1 max-w-7xl mx-auto w-full px-3 sm:px-4 py-4 sm:py-6 gap-4 lg:gap-6">
        <aside className="w-full lg:w-52 shrink-0 min-w-0">
          <div className="px-1 pb-2 lg:pb-3 mb-2 border-b border-gray-200">
            <span className="text-sm font-bold text-gray-800">YouTube Monitor</span>
          </div>
          <nav className="flex flex-row lg:flex-col gap-1 overflow-x-auto lg:overflow-x-visible pb-1 lg:pb-0 -mx-1 px-1 lg:mx-0 lg:px-0 bg-white rounded-xl shadow-sm p-2 lg:p-3 lg:sticky lg:top-6">
            {MAIN_NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}

            <div className="flex flex-row lg:flex-col gap-1 lg:border-t lg:border-gray-100 lg:mt-1 lg:pt-1">
              <button
                type="button"
                onClick={() => setSettingsOpen((v) => !v)}
                className={`flex shrink-0 items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors whitespace-nowrap lg:whitespace-normal w-full text-left ${
                  isOnSettings ? 'text-blue-600 font-medium' : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <span>⚙️</span>
                <span className="flex-1">Settings</span>
                <svg
                  className={`w-3.5 h-3.5 shrink-0 transition-transform hidden lg:block ${settingsOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {settingsOpen &&
                SETTINGS_NAV.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `flex shrink-0 items-center gap-2 px-3 lg:pl-7 py-2 rounded-lg text-sm transition-colors whitespace-nowrap lg:whitespace-normal ${
                        isActive ? 'bg-blue-600 text-white font-medium' : 'text-gray-500 hover:bg-gray-100'
                      }`
                    }
                  >
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                  </NavLink>
                ))}
            </div>
          </nav>
        </aside>

        <main className="flex-1 min-w-0 w-full">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
