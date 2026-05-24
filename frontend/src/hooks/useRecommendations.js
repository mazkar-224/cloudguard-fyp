import { useQuery } from '@tanstack/react-query'
import { fetchRecommendations } from '../lib/api'

/*
  useRecommendations — wraps useQuery for GET /recommendations.

  The filter object is part of the queryKey, so changing a filter is a new
  cache entry and React Query refetches automatically. The update mutation and
  the "Scan now" action both invalidate the ['recommendations'] prefix, which
  covers every filter combination at once.

  Usage:
    const { data, isLoading, isError, refetch } = useRecommendations({ resourceType, status })
    // data → { items: [...], total, total_estimated_savings, limit, offset }
*/
export function useRecommendations({ resourceType = 'all', status = 'open' } = {}) {
  return useQuery({
    queryKey: ['recommendations', { resourceType, status }],
    queryFn: () => fetchRecommendations({ resourceType, status }),
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load recommendations' },
  })
}
