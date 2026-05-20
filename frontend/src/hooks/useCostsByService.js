import { useQuery } from '@tanstack/react-query'
import { fetchByService } from '../lib/api'

/*
  useCostsByService — fetches cost totals grouped by service for the last N days,
  then reshapes the data into top-5 + "Other" slices for a donut chart.

  Backend requires explicit start_date / end_date query params (not a `days` shorthand),
  so we compute those dates here from the `days` argument.

  Helper: toLocalISO formats a Date as "YYYY-MM-DD" in the user's local timezone.
  Using .toISOString() instead would give UTC midnight, which could be the wrong
  calendar day for users in UTC+5 (Pakistan) or higher.
*/

function toLocalISO(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function useCostsByService(days = 30) {
  return useQuery({
    queryKey: ['byService', days],
    meta: { errorMessage: 'Could not load service breakdown' },
    queryFn: () => {
      const end = new Date()
      const start = new Date()
      // setDate mutates in place — subtract days from today.
      // JS handles negative values correctly (e.g. setDate(-10) on May rolls back to April).
      start.setDate(start.getDate() - days)
      return fetchByService(toLocalISO(start), toLocalISO(end))
    },
    staleTime: 60_000,
    select: (rows) => {
      if (!rows.length) return []

      const grandTotal = rows.reduce((sum, r) => sum + r.cost, 0)
      if (grandTotal === 0) return []

      const top5 = rows.slice(0, 5)
      const otherCost = rows.slice(5).reduce((sum, r) => sum + r.cost, 0)

      const slices = top5.map((r) => ({
        service: r.service,
        cost: r.cost,
        // Round percentage to one decimal place (e.g. 34.7%)
        pct: Math.round((r.cost / grandTotal) * 1000) / 10,
      }))

      // Only add "Other" slice if there are services beyond the top 5
      if (otherCost > 0) {
        slices.push({
          service: 'Other',
          cost: Math.round(otherCost * 100) / 100,
          pct: Math.round((otherCost / grandTotal) * 1000) / 10,
        })
      }

      return slices
    },
  })
}
