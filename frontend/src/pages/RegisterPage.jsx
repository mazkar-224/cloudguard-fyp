import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { AuthShell, Field, FormError, SubmitButton } from './LoginPage'

/*
  RegisterPage — create an account, then (via AuthContext.register) get logged
  in automatically and dropped onto the dashboard. We validate the password
  length and confirmation client-side so obvious mistakes never reach the API;
  the backend enforces the same min length and the unique-email rule.
*/
function RegisterPage() {
  const { register, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords don’t match.')
      return
    }

    setSubmitting(true)
    try {
      await register(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      // 409 → email already taken; otherwise a generic message.
      setError(
        err.response?.status === 409
          ? 'An account with this email already exists.'
          : 'Something went wrong. Please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Start monitoring your AWS spend">
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
          autoComplete="new-password"
          placeholder="At least 8 characters"
        />
        <Field
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          placeholder="Re-enter your password"
        />

        <SubmitButton submitting={submitting} idle="Create account" busy="Creating account…" />
      </form>

      <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-accent hover:text-accent-dark">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}

export default RegisterPage
