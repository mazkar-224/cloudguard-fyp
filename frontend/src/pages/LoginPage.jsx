import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ShieldCheck, Loader2, AlertCircle } from 'lucide-react'

import { useAuth } from '../auth/AuthContext'

/*
  LoginPage — email + password → token. On success we send the user to wherever
  they were originally headed (ProtectedRoute stashes it in router state), or to
  the dashboard. Errors are shown inline so a wrong password never redirects.
*/
function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const redirectTo = location.state?.from?.pathname || '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Already logged in? Skip the form entirely.
  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      // 401 → bad credentials; anything else → generic message.
      setError(
        err.response?.status === 401
          ? 'Incorrect email or password.'
          : 'Something went wrong. Please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your CloudGuard dashboard">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <FormError message={error} />}

        <Field
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@example.com"
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          placeholder="••••••••"
        />

        <SubmitButton submitting={submitting} idle="Sign in" busy="Signing in…" />
      </form>

      <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
        Don’t have an account?{' '}
        <Link to="/register" className="font-medium text-accent hover:text-accent-dark">
          Create one
        </Link>
      </p>
    </AuthShell>
  )
}

// ── Shared auth UI ──────────────────────────────────────────────────────────
// Kept in this file (and re-exported) so RegisterPage reuses the exact look.

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="p-3 rounded-2xl bg-accent/10 text-accent mb-4">
            <ShieldCheck size={32} strokeWidth={1.75} />
          </div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">{title}</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
          {children}
        </div>
      </div>
    </div>
  )
}

export function Field({ label, type, value, onChange, autoComplete, placeholder }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
        className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent"
      />
    </label>
  )
}

export function FormError({ message }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 px-3 py-2 text-sm text-red-700 dark:text-red-300">
      <AlertCircle size={16} strokeWidth={2} className="shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  )
}

export function SubmitButton({ submitting, idle, busy }) {
  return (
    <button
      type="submit"
      disabled={submitting}
      className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-accent rounded-md hover:bg-accent-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {submitting && <Loader2 size={16} className="animate-spin" />}
      {submitting ? busy : idle}
    </button>
  )
}

export default LoginPage
