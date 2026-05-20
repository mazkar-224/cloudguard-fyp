import { useLocation } from 'react-router-dom'
import { RefreshCw, Sun, Moon } from 'lucide-react'
import { useDarkMode } from '../hooks/useDarkMode'
import { useSync } from '../hooks/useSync'

const PAGE_TITLES = {
  '/':         'Dashboard',
  '/alerts':   'Alerts',
  '/settings': 'Settings',
}

function Header() {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] ?? 'CloudGuard'

  const [dark, setDark] = useDarkMode()
  const { sync, syncing } = useSync()

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

        {/* Sync now button */}
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

      </div>
    </header>
  )
}

export default Header
