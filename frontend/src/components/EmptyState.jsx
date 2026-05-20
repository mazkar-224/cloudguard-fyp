import { CloudOff } from 'lucide-react'

/*
  EmptyState — shown in place of charts/tables when there is no data.

  Props:
    icon    — lucide-react icon component (defaults to CloudOff)
    heading — short primary message,  e.g. "No data yet"
    subtext — optional secondary line, e.g. "Run your first sync to populate cost data"
    action  — optional { label: string, onClick: fn, disabled?: boolean }
               renders a primary button below the text
*/
function EmptyState({
  icon: Icon = CloudOff,
  heading,
  subtext,
  action,
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2 text-center">

      {/* Icon */}
      <Icon
        size={36}
        strokeWidth={1.5}
        className="text-gray-300 dark:text-gray-600 mb-1"
      />

      {/* Primary message */}
      <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
        {heading}
      </p>

      {/* Secondary message */}
      {subtext && (
        <p className="text-xs text-gray-400 dark:text-gray-500 max-w-xs">
          {subtext}
        </p>
      )}

      {/* Optional CTA button */}
      {action && (
        <button
          onClick={action.onClick}
          disabled={action.disabled}
          className="mt-3 px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

export default EmptyState
