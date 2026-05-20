// ── Real card ─────────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  valueColor = 'text-gray-900 dark:text-white',
  subtext,
  subtextColor = 'text-gray-500 dark:text-gray-400',
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        {title}
      </p>
      <p className={`text-2xl font-bold mt-2 ${valueColor}`}>
        {value}
      </p>
      {subtext && (
        <p className={`text-sm mt-1 ${subtextColor}`}>
          {subtext}
        </p>
      )}
    </div>
  )
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

export function SkeletonCard() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 animate-pulse">
      <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-2/5 mb-3" />
      <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-3/5 mb-2" />
      <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/4" />
    </div>
  )
}

// ── Error card ────────────────────────────────────────────────────────────────

export function ErrorCard({ title, onRetry }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-red-200 dark:border-red-800 p-6">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        {title}
      </p>
      <p className="text-sm text-danger mt-2">Failed to load</p>
      <button
        onClick={onRetry}
        className="mt-3 text-xs font-medium text-accent hover:underline"
      >
        Retry
      </button>
    </div>
  )
}

export default StatCard
