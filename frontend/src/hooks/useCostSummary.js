import { useQuery } from '@tanstack/react-query'
import { fetchSummary } from '../lib/api'

/*
  useCostSummary — custom hook that wraps useQuery for /costs/summary.

  Why a custom hook instead of calling useQuery directly in the component?
    - The component only needs to say "give me the 30-day summary"
    - The hook owns the queryKey naming convention and staleTime config
    - If we ever change the API call (pagination, caching rules), we change it here once

  Usage:
    const { data, isLoading, isError, refetch } = useCostSummary(30)
*/
export function useCostSummary(days) {
  return useQuery({
    queryKey: ['summary', days],
    queryFn: () => fetchSummary(days),
    staleTime: 60_000,
    meta: { errorMessage: 'Could not load cost summary' },
  })
}
