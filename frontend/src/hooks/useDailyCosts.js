import { useQuery } from '@tanstack/react-query'
import { fetchDailyCosts } from '../lib/api'

/*
  useDailyCosts — fetches per-day cost rows and groups them into one total per day.

  Backend returns:  [{ date: "2026-05-01", service: "EC2", cost: 12.34 }, ...]
  One date appears once per service — multiple rows for the same day.

  The `select` option transforms the raw array before the component sees it:
    - Groups rows by date, sums all services into a single total
    - Produces two date strings per entry:
        date:     "May 1"       → short label for the X-axis tick
        fullDate: "May 1, 2026" → full label shown in the tooltip
    - Sorts ascending so the chart reads left → right chronologically
*/
export function useDailyCosts(days = 30) {
  return useQuery({
    queryKey: ['dailyCosts', days],
    queryFn: () => fetchDailyCosts(days),
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load daily costs' },
    select: (rows) => {
      // Accumulate totals keyed on the raw ISO date string ("2026-05-01")
      // so the sort below works correctly (ISO strings sort alphabetically = chronologically)
      const byDate = {}
      for (const row of rows) {
        byDate[row.date] = (byDate[row.date] ?? 0) + row.cost
      }

      return Object.entries(byDate)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([isoDate, total]) => {
          // Append T00:00:00 so new Date() treats the string as local time,
          // not UTC midnight — avoids the date appearing one day behind in UTC+5.
          const d = new Date(isoDate + 'T00:00:00')
          return {
            date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            fullDate: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
            total: Math.round(total * 100) / 100,
          }
        })
    },
  })
}
