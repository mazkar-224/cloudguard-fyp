import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Bell, Lightbulb, Settings } from 'lucide-react'

import { useAlertCounts } from '../hooks/useAlertCounts'

const NAV_ITEMS = [
  { to: '/',                label: 'Dashboard',       icon: LayoutDashboard },
  { to: '/alerts',          label: 'Alerts',          icon: Bell },
  { to: '/recommendations', label: 'Recommendations', icon: Lightbulb },
  { to: '/settings',        label: 'Settings',        icon: Settings },
]

function Sidebar() {
  const { data: counts } = useAlertCounts()
  const newCount = counts?.by_status?.new ?? 0

  return (
    <aside className="w-60 shrink-0 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 sticky top-14 h-[calc(100vh-3.5rem)] flex flex-col">

      <div className="px-4 py-5 border-b border-gray-100 dark:border-gray-800">
        <span className="text-sm font-semibold text-gray-900 dark:text-white tracking-tight">
          CloudGuard
        </span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
              ].join(' ')
            }
          >
            <Icon size={16} strokeWidth={1.75} />
            {label}
            {to === '/alerts' && newCount > 0 && (
              <span className="ml-auto inline-flex items-center justify-center min-w-5 h-5 px-1.5 text-xs font-semibold rounded-full bg-danger text-white">
                {newCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

    </aside>
  )
}

export default Sidebar
