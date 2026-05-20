import { useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { BarChart2 } from 'lucide-react'
import { useDailyCosts } from '../../hooks/useDailyCosts'
import { useSync } from '../../hooks/useSync'
import EmptyState from '../EmptyState'

// ── Helpers ───────────────────────────────────────────────────────────────────

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

function formatYAxis(value) {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`
  if (value >= 1)    return `$${value.toFixed(0)}`
  return `$${value.toFixed(2)}`
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { fullDate, total } = payload[0].payload
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm px-3 py-2 text-sm">
      <p className="text-gray-500 dark:text-gray-400">{fullDate}</p>
      <p className="font-semibold text-accent mt-0.5">{usd.format(total)}</p>
    </div>
  )
}

// ── Range selector config ─────────────────────────────────────────────────────

const RANGES = [
  { label: '7d',  days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
]

// ── Main component ────────────────────────────────────────────────────────────

function DailyCostsChart() {
  const [days, setDays] = useState(30)
  const { data, isLoading, isError, refetch } = useDailyCosts(days)
  const { sync, syncing } = useSync()

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">

      {/* Header row — always visible even during loading */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          Daily spend
        </p>

        <div className="flex rounded-md border border-gray-200 dark:border-gray-700 overflow-hidden">
          {RANGES.map(({ label, days: d }) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={[
                'px-3 py-1 text-xs font-medium transition-colors',
                d !== 7 ? 'border-l border-gray-200 dark:border-gray-700' : '',
                days === d
                  ? 'bg-accent text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart body */}
      {isLoading ? (
        <div className="h-[220px] bg-gray-50 dark:bg-gray-700 rounded-lg animate-pulse" />

      ) : isError ? (
        <div className="h-[220px] flex items-center justify-between px-2">
          <p className="text-sm text-danger">Failed to load daily costs</p>
          <button onClick={refetch} className="text-sm text-accent hover:underline">Retry</button>
        </div>

      ) : !data || data.length === 0 ? (
        /*
          EmptyState with a sync CTA — this is what the user sees before
          their first sync run. The button calls useSync so it shares the
          same logic (spinner, toast) as the header Sync Now button.
        */
        <EmptyState
          icon={BarChart2}
          heading="No cost data yet"
          subtext="Run a sync to pull your AWS costs into the dashboard."
          action={{
            label: syncing ? 'Syncing…' : 'Run first sync',
            onClick: sync,
            disabled: syncing,
          }}
        />

      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            {/*
              stroke uses the CSS variable defined in index.css so the grid
              line color adapts to dark mode — SVG props can't use dark: classes.
            */}
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--chart-grid-color)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={formatYAxis}
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="total"
              stroke="var(--color-accent)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0, fill: 'var(--color-accent)' }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default DailyCostsChart
