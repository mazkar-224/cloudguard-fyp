import { useLocation, useNavigate } from 'react-router-dom'
import { RefreshCw, Search, Sun, Moon, LogOut } from 'lucide-react'
import { useDarkMode } from '../hooks/useDarkMode'
import { useSync } from '../hooks/useSync'
import { useScanResources } from '../hooks/useScanResources'
import { useAuth } from '../auth/AuthContext'

const PAGE_TITLES = {
  '/':                'Dashboard',
  '/alerts':          'Alerts',
  '/recommendations': 'Recommendations',
  '/settings':        'Settings',
}

function Header() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const title = PAGE_TITLES[pathname] ?? 'CloudGuard'

  const [dark, setDark] = useDarkMode()
  const { sync, syncing } = useSync()
  const { scan, scanning } = useScanResources()
  const { user, logout } = useAuth()

  // "Scan now" triggers a live AWS resource scan — only relevant on the
  // Recommendations page, so it appears there instead of the global Sync now.
  const onRecommendations = pathname === '/recommendations'

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="h-14 sticky top-0 z-10 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-6">

      <h1 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h1>

      <div className="flex items-center gap-2">

        {/* Dark / light mode toggle */}
        <button
          type="button"
          onClick={() => setDark(d => !d)}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {dark ? <Sun size={16} strokeWidth={2} /> : <Moon size={16} strokeWidth={2} />}
        </button>

        {/* Scan now (Recommendations page) / Sync now (everywhere else) */}
        {onRecommendations ? (
          <button
            type="button"
            onClick={scan}
            disabled={scanning}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className={scanning ? 'animate-spin' : ''}>
              <Search size={14} strokeWidth={2} />
            </span>
            {scanning ? 'Scanning…' : 'Scan now'}
          </button>
        ) : (
          <button
            type="button"
            onClick={sync}
            disabled={syncing}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className={syncing ? 'animate-spin' : ''}>
              <RefreshCw size={14} strokeWidth={2} />
            </span>
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
        )}

        {/* Divider + account section */}
        <div className="h-5 w-px bg-gray-200 dark:bg-gray-700 mx-1" />

        {user?.email && (
          <span
            className="hidden sm:inline text-xs text-gray-500 dark:text-gray-400 max-w-[14rem] truncate"
            title={user.email}
          >
            {user.email}
          </span>
        )}

        {/* Logout — clears the session and returns to the login screen */}
        <button
          type="button"
          onClick={handleLogout}
          aria-label="Log out"
          title="Log out"
          className="p-1.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-danger transition-colors"
        >
          <LogOut size={16} strokeWidth={2} />
        </button>

      </div>
    </header>
  )
}

export default Header
