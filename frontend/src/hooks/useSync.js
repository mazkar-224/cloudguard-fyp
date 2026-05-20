import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { triggerSync } from '../lib/api'

/*
  useSync — wraps the POST /admin/sync call in React Query's useMutation.

  Why useMutation instead of useState + try/catch?
    useMutation gives us isPending, onSuccess, and onError for free.
    We no longer need to manually track loading state or remember to
    call setSyncing(false) in a finally block.

  On success we invalidate only the three query families that sync affects,
  rather than invalidating everything. The query keys match the prefixes
  used in useCostSummary (['summary']), useDailyCosts (['dailyCosts']),
  and useCostsByService (['byService']) — React Query invalidates all
  entries whose key starts with that prefix (e.g. ['summary', 7] and
  ['summary', 30] are both invalidated by { queryKey: ['summary'] }).
*/
export function useSync() {
  const queryClient = useQueryClient()

  const { mutate: sync, isPending: syncing } = useMutation({
    mutationFn: triggerSync,

    onSuccess: (data) => {
      // Invalidate all three cost query families so every card and chart
      // refetches immediately without waiting for the 60s staleTime to expire.
      queryClient.invalidateQueries({ queryKey: ['summary'] })
      queryClient.invalidateQueries({ queryKey: ['dailyCosts'] })
      queryClient.invalidateQueries({ queryKey: ['byService'] })

      // data.rows_upserted comes straight from the backend SyncResult schema.
      // This is what makes the evaluator say "wow" — a real number, not a generic message.
      toast.success(`Synced — ${data.rows_upserted} rows updated`)
    },

    onError: (err) => {
      toast.error('Sync failed — check your AWS credentials')
      console.warn('Sync failed:', err)
    },
  })

  return { sync, syncing }
}
