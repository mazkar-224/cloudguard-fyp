import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  deleteAwsCredentials,
  fetchAwsCredentials,
  saveAwsCredentials,
} from '../lib/api'

/*
  Hooks backing the Settings page's AWS-credential management.

  - useAwsCredentials(): the masked saved credential (last-4 + region), or null.
  - useSaveAwsCredentials(): save/replace; on success refreshes the masked view
    AND the cost/recommendation data, since changing the account changes them.
  - useDeleteAwsCredentials(): remove the saved credential.

  Pulling a friendly message off the backend's `detail` field keeps the toasts
  specific (e.g. "AWS rejected these credentials: Access denied …").
*/

const QUERY_KEY = ['awsCredentials']

function apiMessage(err, fallback) {
  return err?.response?.data?.detail || fallback
}

export function useAwsCredentials() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAwsCredentials,
  })
}

export function useSaveAwsCredentials() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: saveAwsCredentials,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
      // The account behind every dollar figure just changed — refresh them too.
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
      queryClient.invalidateQueries({ queryKey: ['recommendationsSummary'] })
      toast.success('AWS credentials saved')
    },
    onError: (err) => {
      toast.error(apiMessage(err, 'Could not save credentials'))
    },
  })
}

export function useDeleteAwsCredentials() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: deleteAwsCredentials,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
      toast.success('AWS credentials removed')
    },
    onError: (err) => {
      toast.error(apiMessage(err, 'Could not remove credentials'))
    },
  })
}
