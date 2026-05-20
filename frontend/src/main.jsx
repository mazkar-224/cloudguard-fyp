import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, QueryCache } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { toast } from 'sonner'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'

/*
  QueryCache.onError is the React Query v5 way to handle query errors globally.
  (The per-query `onError` option was removed in v5.)

  Each hook can pass a friendly message via query.meta.errorMessage.
  If meta is missing, we show a generic fallback.

  retry: 1 means React Query tries the request once, then retries once more
  before calling onError — so one failure shows one toast, not three.
*/
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (_error, query) => {
      const msg = query.meta?.errorMessage ?? 'Failed to load data'
      toast.error(msg)
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/*
      ErrorBoundary sits outside QueryClientProvider so it can catch errors
      from both React Query internals and our own components.
    */}
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
)
