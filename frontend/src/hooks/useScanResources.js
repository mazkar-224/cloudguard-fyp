import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { triggerResourceScan } from '../lib/api'

/*
  useScanResources — wraps POST /admin/scan-resources in useMutation.

  This is the live-demo trigger: it runs a real AWS resource scan, then
  invalidates the recommendations list and summary so freshly-found waste and
  the new dollar total appear without a manual refresh. Mirrors useSync.

  Usage:
    const { scan, scanning } = useScanResources()
    <button onClick={scan} disabled={scanning}>{scanning ? 'Scanning…' : 'Scan now'}</button>
*/
export function useScanResources() {
  const queryClient = useQueryClient()

  const { mutate: scan, isPending: scanning } = useMutation({
    mutationFn: triggerResourceScan,

    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['recommendationsSummary'] })

      // recommendations_upserted comes straight from the backend ScanResult —
      // a real number is what makes the live demo land.
      toast.success(`Scan complete — ${data.recommendations_upserted} recommendation(s)`)
    },

    onError: (err) => {
      toast.error('Scan failed — check your AWS credentials')
      console.warn('Resource scan failed:', err)
    },
  })

  return { scan, scanning }
}
