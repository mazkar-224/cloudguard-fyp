import { TrendingUp, TrendingDown } from 'lucide-react'
import { useCostSummary } from '../../hooks/useCostSummary'
import { SkeletonCard, ErrorCard } from '../StatCard'
import StatCard from '../StatCard'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

// ── Percent-change card ───────────────────────────────────────────────────────

function PctChangeCard() {
  const q7  = useCostSummary(7)
  const q14 = useCostSummary(14)

  if (q7.isLoading || q14.isLoading) return <SkeletonCard />

  if (q7.isError || q14.isError) {
    return (
      <ErrorCard
        title="vs last week"
        onRetry={() => { q7.refetch(); q14.refetch() }}
      />
    )
  }

  const thisWeek = q7.data.total_usd
  const prevWeek = q14.data.total_usd - q7.data.total_usd
  const hasPrior = prevWeek > 0

  const pct     = hasPrior ? ((thisWeek - prevWeek) / prevWeek) * 100 : null
  const isDown  = pct !== null && pct <= 0
  const isUp    = pct !== null && pct > 0
  const color   = pct === null ? 'text-gray-400 dark:text-gray-500' : isDown ? 'text-success' : 'text-danger'
  const display = pct === null ? '—' : `${isUp ? '+' : ''}${pct.toFixed(1)}%`
  const subtext = pct === null ? 'No prior week data' : isDown ? 'Spending down' : 'Spending up'

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        vs last week
      </p>
      <div className={`flex items-center gap-2 mt-2 ${color}`}>
        <span className="text-2xl font-bold">{display}</span>
        {isDown && <TrendingDown size={20} strokeWidth={2} />}
        {isUp   && <TrendingUp   size={20} strokeWidth={2} />}
      </div>
      <p className={`text-sm mt-1 ${color}`}>{subtext}</p>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

function SummaryCards() {
  const q30 = useCostSummary(30)
  const q1  = useCostSummary(1)
  const q7  = useCostSummary(7)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">

      {q30.isLoading ? (
        <SkeletonCard />
      ) : q30.isError ? (
        <ErrorCard title="30-day total" onRetry={q30.refetch} />
      ) : q30.data ? (
        <StatCard
          title="30-day total"
          value={usd.format(q30.data.total_usd)}
          subtext={`${q30.data.record_count} records · ${q30.data.source}`}
        />
      ) : null}

      {q7.isLoading ? (
        <SkeletonCard />
      ) : q7.isError ? (
        <ErrorCard title="7-day total" onRetry={q7.refetch} />
      ) : q7.data ? (
        <StatCard
          title="7-day total"
          value={usd.format(q7.data.total_usd)}
          subtext={`${q7.data.record_count} records`}
        />
      ) : null}

      {q1.isLoading ? (
        <SkeletonCard />
      ) : q1.isError ? (
        <ErrorCard title="Yesterday" onRetry={q1.refetch} />
      ) : q1.data ? (
        <StatCard
          title="Yesterday"
          value={usd.format(q1.data.total_usd)}
          subtext={
            q1.data.record_count > 0
              ? `${q1.data.record_count} services billed`
              : 'No charges yesterday'
          }
        />
      ) : null}

      <PctChangeCard />

    </div>
  )
}

export default SummaryCards
