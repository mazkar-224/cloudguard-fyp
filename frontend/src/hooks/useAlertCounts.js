import { useQuery } from '@tanstack/react-query'
import { fetchAlertCounts } from '../lib/api'

/*
  useAlertCounts — wraps useQuery for GET /alerts/count.

  Used by the sidebar badge (by_status.new) and could feed filter chips later.
  Uses the same default 30-day window as the alerts list so the badge count
  never disagrees with what the list shows.

  Usage:
    const { data } = useAlertCounts()
    // data → { by_status: {new, acknowledged}, by_severity: {...}, total }
*/
export function useAlertCounts(days = 30) {
  return useQuery({
    queryKey: ['alertCounts', days],
    queryFn: () => fetchAlertCounts(days),
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load alert counts' },
  })
}
