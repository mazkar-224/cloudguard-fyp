import { useQuery } from '@tanstack/react-query'
import { fetchAlerts } from '../lib/api'

/*
  useAlerts — wraps useQuery for GET /alerts.

  The filter object is part of the queryKey, so changing a filter is a new
  cache entry and React Query refetches automatically. The acknowledge
  mutation invalidates the ['alerts'] prefix, which covers every filter
  combination at once.

  Usage:
    const { data, isLoading, isError, refetch } = useAlerts({ status, severity, days })
    // data → { items: [...], total, limit, offset }
*/
export function useAlerts({ status = 'all', severity = 'all', days = 30 } = {}) {
  return useQuery({
    queryKey: ['alerts', { status, severity, days }],
    queryFn: () => fetchAlerts({ status, severity, days }),
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load alerts' },
  })
}
