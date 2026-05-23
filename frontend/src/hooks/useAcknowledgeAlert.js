import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { acknowledgeAlert } from '../lib/api'

/*
  useAcknowledgeAlert — wraps PATCH /alerts/{id} in useMutation.

  On success we invalidate both the alerts list AND the counts, so the card
  flips to "Acknowledged" and the sidebar badge ticks down the moment the
  request returns — same pattern as useSync.

  pendingId exposes the id currently being acknowledged so the page can show a
  per-card pending state (only the clicked card's button disables, not all).

  Usage:
    const { acknowledge, pendingId } = useAcknowledgeAlert()
    <button onClick={() => acknowledge(alert.id)} disabled={pendingId === alert.id}>
*/
export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: acknowledgeAlert,

    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alertCounts'] })
      toast.success('Alert acknowledged')
    },

    onError: (err) => {
      toast.error('Could not acknowledge alert')
      console.warn('Acknowledge failed:', err)
    },
  })

  return {
    acknowledge: mutation.mutate,
    pendingId: mutation.isPending ? mutation.variables : null,
  }
}
