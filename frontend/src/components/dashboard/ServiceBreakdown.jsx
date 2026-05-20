import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { PieChart as PieIcon } from 'lucide-react'
import { useCostsByService } from '../../hooks/useCostsByService'
import { useSync } from '../../hooks/useSync'
import EmptyState from '../EmptyState'

const SLICE_COLORS = [
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#9ca3af', // gray-400 — "Other"
]

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

// ── Custom tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { service, cost, pct } = payload[0].payload
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm px-3 py-2 text-sm">
      <p className="font-medium text-gray-700 dark:text-gray-200">{service}</p>
      <p className="text-gray-500 dark:text-gray-400 mt-0.5">
        {usd.format(cost)} · <span className="font-medium">{pct}%</span>
      </p>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

function ServiceBreakdown() {
  const { data, isLoading, isError, refetch } = useCostsByService(30)
  const { sync, syncing } = useSync()

  // ── Loading ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <div className="h-3.5 w-28 bg-gray-100 dark:bg-gray-700 rounded animate-pulse mb-4" />
        <div className="flex justify-center my-2">
          <div className="relative w-40 h-40">
            <div className="absolute inset-0 rounded-full bg-gray-100 dark:bg-gray-700 animate-pulse" />
            {/* Donut hole — must match card bg */}
            <div className="absolute inset-8 rounded-full bg-white dark:bg-gray-800" />
          </div>
        </div>
        <div className="mt-4 space-y-2">
          {[70, 55, 45, 35].map((w) => (
            <div key={w} className="h-3 bg-gray-50 dark:bg-gray-700 rounded animate-pulse" style={{ width: `${w}%` }} />
          ))}
        </div>
      </div>
    )
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 flex items-center justify-between">
        <p className="text-sm text-danger">Failed to load service breakdown</p>
        <button onClick={refetch} className="text-sm text-accent hover:underline">Retry</button>
      </div>
    )
  }

  // ── Empty ─────────────────────────────────────────────────────────────────
  if (!data || data.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
          Top services — last 30 days
        </p>
        <EmptyState
          icon={PieIcon}
          heading="No service data yet"
          subtext="Run a sync to see which AWS services are costing the most."
          action={{
            label: syncing ? 'Syncing…' : 'Run first sync',
            onClick: sync,
            disabled: syncing,
          }}
        />
      </div>
    )
  }

  // ── Data ──────────────────────────────────────────────────────────────────
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
        Top services — last 30 days
      </p>

      <ResponsiveContainer width="100%" height={190}>
        <PieChart>
          <Pie
            data={data}
            dataKey="cost"
            nameKey="service"
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={82}
            paddingAngle={2}
            strokeWidth={0}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={SLICE_COLORS[i % SLICE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>

      <ul className="mt-1 space-y-2">
        {data.map((item, i) => (
          <li key={item.service} className="flex items-center justify-between text-xs gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: SLICE_COLORS[i % SLICE_COLORS.length] }}
              />
              <span className="text-gray-600 dark:text-gray-300 truncate">{item.service}</span>
            </div>
            <span className="text-gray-400 dark:text-gray-500 font-medium shrink-0">{item.pct}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ServiceBreakdown
