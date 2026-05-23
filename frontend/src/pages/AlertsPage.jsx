import { useState } from 'react'
import { Bell, AlertTriangle, Check } from 'lucide-react'

import { useAlerts } from '../hooks/useAlerts'
import { useAcknowledgeAlert } from '../hooks/useAcknowledgeAlert'
import EmptyState from '../components/EmptyState'

// ── Filter options ────────────────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'acknowledged', label: 'Acknowledged' },
]

const SEVERITY_OPTIONS = [
  { value: 'all', label: 'All severities' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

// Severity badge colours — readable on both light and dark backgrounds.
// low = neutral, medium = amber, high = red.
const SEVERITY_BADGE = {
  low: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
  medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

// ── Formatters ──────────────────────────────────────────────────────────────

// alert_date is a plain "YYYY-MM-DD" string. Append a local midnight so the
// Date isn't parsed as UTC (which can shift the displayed day by one).
const fmtDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })

const usd = (n) =>
  `$${Number(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

// ── Alert card ────────────────────────────────────────────────────────────────

function AlertCard({ alert, onAcknowledge, acknowledging }) {
  const scopeLabel = alert.scope === 'total' ? 'Total spend' : alert.service_name
  const badgeClass = SEVERITY_BADGE[alert.severity] ?? SEVERITY_BADGE.low

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 flex flex-col gap-3">

      {/* Header: scope + date, severity badge on the right */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">{scopeLabel}</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{fmtDate(alert.alert_date)}</p>
        </div>
        <span className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-full capitalize ${badgeClass}`}>
          {alert.severity}
        </span>
      </div>

      {/* Amount vs baseline + z-score */}
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div>
          <span className="text-lg font-bold text-gray-900 dark:text-white">{usd(alert.amount_usd)}</span>
          <span className="text-xs text-gray-400 dark:text-gray-500 ml-1.5">spent</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          normally {usd(alert.baseline_mean)}
          <span className="mx-1.5 text-gray-300 dark:text-gray-600">·</span>
          z-score {Number(alert.z_score).toFixed(2)}
        </p>
      </div>

      {/* Action / status footer */}
      <div className="flex justify-end pt-1">
        {alert.status === 'new' ? (
          <button
            onClick={() => onAcknowledge(alert.id)}
            disabled={acknowledging}
            className="px-3 py-1.5 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {acknowledging ? 'Acknowledging…' : 'Acknowledge'}
          </button>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
            <Check size={14} strokeWidth={2.5} />
            Acknowledged
          </span>
        )}
      </div>
    </div>
  )
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function AlertCardSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="space-y-2">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-20" />
        </div>
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded-full w-14" />
      </div>
      <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-2/5" />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function AlertsPage() {
  const [status, setStatus] = useState('all')
  const [severity, setSeverity] = useState('all')

  const { data, isLoading, isError, refetch } = useAlerts({ status, severity, days: 30 })
  const { acknowledge, pendingId } = useAcknowledgeAlert()

  const alerts = data?.items ?? []

  return (
    <div className="p-6 space-y-6">

      {/* Section label */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Alerts</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Unusual AWS spend detected over the last 30 days
        </p>
      </div>

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

        {/* Severity dropdown */}
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="text-sm rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {SEVERITY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* ── Content states ── */}

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <AlertCardSkeleton key={i} />)}
        </div>
      )}

      {isError && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-red-200 dark:border-red-800 p-8 flex flex-col items-center gap-2 text-center">
          <AlertTriangle size={32} strokeWidth={1.5} className="text-danger" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">Couldn’t load alerts</p>
          <button
            onClick={() => refetch()}
            className="mt-2 px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && alerts.length === 0 && (
        <EmptyState
          icon={Bell}
          heading="No alerts"
          subtext={
            status !== 'all' || severity !== 'all'
              ? 'No alerts match these filters. Try widening them.'
              : 'Nothing unusual detected. Alerts appear here when spend spikes.'
          }
        />
      )}

      {!isLoading && !isError && alerts.length > 0 && (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onAcknowledge={acknowledge}
              acknowledging={pendingId === alert.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default AlertsPage
