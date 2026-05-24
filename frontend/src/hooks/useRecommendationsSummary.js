import { useQuery } from '@tanstack/react-query'
import { fetchRecommendationsSummary } from '../lib/api'

/*
  useRecommendationsSummary — wraps useQuery for GET /recommendations/summary.

  Feeds the "Potential savings: $X/month" hero banner. Scoped to open
  recommendations on the backend. Invalidated by both the update mutation and
  the "Scan now" action so the headline number stays in sync with the list.

  Usage:
    const { data } = useRecommendationsSummary()
    // data → { total_monthly_savings, open_count, by_resource_type: [...] }
*/
export function useRecommendationsSummary() {
  return useQuery({
    queryKey: ['recommendationsSummary'],
    queryFn: fetchRecommendationsSummary,
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load savings summary' },
  })
}
