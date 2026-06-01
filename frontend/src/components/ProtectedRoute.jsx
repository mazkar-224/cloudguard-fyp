import { Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { useAuth } from '../auth/AuthContext'

/*
  ProtectedRoute — wraps the authenticated part of the app.

  - While the AuthContext is still validating a stored token (`initializing`),
    we show a spinner. This is what lets a logged-in user refresh the page
    without being flashed to /login before /auth/me has a chance to confirm them.
  - Once we know the answer: render the children if authenticated, otherwise
    redirect to /login. We stash the attempted location in router state so the
    login page could send the user back where they were headed.
*/
function ProtectedRoute({ children }) {
  const { isAuthenticated, initializing } = useAuth()
  const location = useLocation()

  if (initializing) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
        <Loader2 size={28} className="animate-spin text-accent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}

export default ProtectedRoute
