import { useState } from 'react'
import {
  Wallet,
  HardDrive,
  Globe,
  Server,
  Camera,
  Gauge,
  Box,
  Sparkles,
  AlertTriangle,
  Check,
  X,
} from 'lucide-react'

import { useRecommendations } from '../hooks/useRecommendations'
import { useRecommendationsSummary } from '../hooks/useRecommendationsSummary'
import { useUpdateRecommendation } from '../hooks/useUpdateRecommendation'
import { useScanResources } from '../hooks/useScanResources'
import EmptyState from '../components/EmptyState'

// ── Filter options ────────────────────────────────────────────────────────────

const RESOURCE_TYPE_OPTIONS = [
  { value: 'all', label: 'All resource types' },
  { value: 'ebs_volume', label: 'EBS Volume' },
  { value: 'elastic_ip', label: 'Elastic IP' },
  { value: 'ec2_instance', label: 'Stopped EC2' },
  { value: 'ebs_snapshot', label: 'EBS Snapshot' },
  { value: 'ec2_instance_idle', label: 'Idle EC2' },
]

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'resolved', label: 'Resolved' },
]

// Per-resource-type icon + human label. Unknown types fall back to a generic box.
const RESOURCE_META = {
  ebs_volume: { label: 'EBS Volume', Icon: HardDrive },
  elastic_ip: { label: 'Elastic IP', Icon: Globe },
  ec2_instance: { label: 'Stopped EC2 Instance', Icon: Server },
  ebs_snapshot: { label: 'EBS Snapshot', Icon: Camera },
  ec2_instance_idle: { label: 'Idle EC2 Instance', Icon: Gauge },
}
const DEFAULT_META = { label: 'Resource', Icon: Box }

// ── Formatter ──────────────────────────────────────────────────────────────────

const usd = (n) =>
  `$${Number(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

// ── Hero banner ────────────────────────────────────────────────────────────────

function HeroBanner({ summary, isLoading }) {
  return (
    <div className="rounded-xl border border-blue-100 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/40 p-6 flex items-center gap-5">
      <div className="shrink-0 p-3 rounded-xl bg-blue-100 dark:bg-blue-900/60 text-blue-600 dark:text-blue-400">
        <Wallet size={28} strokeWidth={1.75} />
      </div>

      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-blue-600/80 dark:text-blue-400/80">
          Potential savings
        </p>

        {isLoading ? (
          <div className="h-9 w-44 mt-1 bg-blue-100 dark:bg-blue-900/60 rounded animate-pulse" />
        ) : (
          <p className="text-3xl font-bold text-gray-900 dark:text-white leading-tight">
            {usd(summary?.total_monthly_savings ?? 0)}
            <span className="text-base font-medium text-gray-500 dark:text-gray-400">/month</span>
          </p>
        )}

        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {isLoading
            ? 'Calculating…'
            : `${summary?.open_count ?? 0} open recommendation${
                (summary?.open_count ?? 0) === 1 ? '' : 's'
              }`}
        </p>
      </div>
    </div>
  )
}

// ── Recommendation card ──────────────────────────────────────────────────────

function RecommendationCard({ rec, onUpdate, pending }) {
  const meta = RESOURCE_META[rec.resource_type] ?? DEFAULT_META
  const Icon = meta.Icon

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 flex flex-col gap-3">
      <div className="flex items-start gap-4">
        {/* Resource-type icon */}
        <div className="shrink-0 p-2.5 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300">
          <Icon size={20} strokeWidth={1.75} />
        </div>

        {/* Identity + reason */}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">{meta.label}</p>
          <p className="text-xs font-mono text-gray-400 dark:text-gray-500 mt-0.5 truncate">
            {rec.resource_id}
            <span className="mx-1.5 text-gray-300 dark:text-gray-600">·</span>
            {rec.region}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">{rec.reason}</p>
        </div>

        {/* Estimated saving — the prominent number */}
        <div className="shrink-0 text-right">
          <p className="text-xl font-bold text-success leading-tight">
            {usd(rec.estimated_monthly_usd)}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">/month</p>
        </div>
      </div>

      {/* Action / status footer */}
      <div className="flex items-center justify-end gap-2 pt-1">
        {rec.status === 'open' ? (
          <>
            <button
              onClick={() => onUpdate({ id: rec.id, status: 'dismissed' })}
              disabled={pending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <X size={14} strokeWidth={2} />
              Dismiss
            </button>
            <button
              onClick={() => onUpdate({ id: rec.id, status: 'resolved' })}
              disabled={pending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Check size={14} strokeWidth={2.5} />
              {pending ? 'Saving…' : 'Mark resolved'}
            </button>
          </>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-400 dark:text-gray-500 capitalize">
            <Check size={14} strokeWidth={2.5} />
            {rec.status}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function CardSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="h-10 w-10 rounded-lg bg-gray-200 dark:bg-gray-700" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-48" />
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-3/5" />
        </div>
        <div className="h-6 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function RecommendationsPage() {
  const [resourceType, setResourceType] = useState('all')
  const [status, setStatus] = useState('open')

  const { data, isLoading, isError, refetch } = useRecommendations({ resourceType, status })
  const { update, pendingId } = useUpdateRecommendation()
  const { data: summary, isLoading: summaryLoading } = useRecommendationsSummary()
  const { scan, scanning } = useScanResources()

  const recs = data?.items ?? []
  const filtersActive = resourceType !== 'all' || status !== 'open'

  return (
    <div className="p-6 space-y-6">
      {/* Section label */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Recommendations</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Wasteful AWS resources, ranked by how much you could save each month
        </p>
      </div>

      {/* Hero savings banner */}
      <HeroBanner summary={summary} isLoading={summaryLoading} />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Status segmented control */}
        <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-0.5">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatus(opt.value)}
              className={[
                'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                status === opt.value
                  ? 'bg-accent text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700',
              ].join(' ')}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Resource type dropdown */}
        <select
          value={resourceType}
          onChange={(e) => setResourceType(e.target.value)}
          className="text-sm rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {RESOURCE_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* ── Content states ── */}

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {isError && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-red-200 dark:border-red-800 p-8 flex flex-col items-center gap-2 text-center">
          <AlertTriangle size={32} strokeWidth={1.5} className="text-danger" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
            Couldn’t load recommendations
          </p>
          <button
            onClick={() => refetch()}
            className="mt-2 px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && recs.length === 0 && (
        <EmptyState
          icon={Sparkles}
          heading="No waste found — nice!"
          subtext={
            filtersActive
              ? 'No recommendations match these filters. Try widening them.'
              : 'Run a scan to check your AWS account for idle and unused resources.'
          }
          action={
            filtersActive
              ? undefined
              : { label: scanning ? 'Scanning…' : 'Scan now', onClick: scan, disabled: scanning }
          }
        />
      )}

      {!isLoading && !isError && recs.length > 0 && (
        <div className="space-y-3">
          {recs.map((rec) => (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              onUpdate={update}
              pending={pendingId === rec.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default RecommendationsPage
