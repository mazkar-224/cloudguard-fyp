import { Component } from 'react'
import { RefreshCw } from 'lucide-react'

/*
  ErrorBoundary — catches JavaScript errors anywhere in the component tree
  and shows a friendly recovery screen instead of a blank white page.

  Why a class component?
    React error boundaries MUST be class components. There is no hook
    equivalent for getDerivedStateFromError or componentDidCatch — this
    is a deliberate React design decision. Functional components cannot
    catch render errors thrown by their children.

  Usage:
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
*/
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  // Called synchronously when a descendant throws during render.
  // Return value merges into component state.
  static getDerivedStateFromError() {
    return { hasError: true }
  }

  // Called after the render phase — safe place to log errors.
  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught a render error:', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    // Recovery screen — centered, works in both light and dark mode
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center px-4">
        <div className="text-center max-w-sm">

          {/* Icon */}
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-50 dark:bg-red-950 mb-4">
            <RefreshCw size={24} className="text-danger" strokeWidth={1.5} />
          </div>

          <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            An unexpected error occurred. Refreshing the page usually fixes it.
          </p>

          <button
            onClick={() => window.location.reload()}
            className="mt-6 px-5 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-dark transition-colors"
          >
            Refresh page
          </button>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
