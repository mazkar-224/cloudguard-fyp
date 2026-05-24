import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { updateRecommendation } from '../lib/api'

/*
  useUpdateRecommendation — wraps PATCH /recommendations/{id} in useMutation.

  On success we invalidate both the recommendations list AND the summary, so
  the dismissed/resolved card drops out of the open list and the hero banner's
  total recalculates the moment the request returns — same pattern as
  useAcknowledgeAlert.

  pendingId exposes the id currently being updated so the page can show a
  per-card pending state (only the clicked card's buttons disable).

  Usage:
    const { update, pendingId } = useUpdateRecommendation()
    <button onClick={() => update({ id: rec.id, status: 'dismissed' })} />
*/
export function useUpdateRecommendation() {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: ({ id, status }) => updateRecommendation(id, status),

    onSuccess: (_data, { status }) => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['recommendationsSummary'] })
      toast.success(
        status === 'dismissed' ? 'Recommendation dismissed' : 'Marked as resolved',
      )
    },

    onError: (err) => {
      toast.error('Could not update recommendation')
      console.warn('Update recommendation failed:', err)
    },
  })

  return {
    update: mutation.mutate,
    pendingId: mutation.isPending ? mutation.variables?.id : null,
  }
}
