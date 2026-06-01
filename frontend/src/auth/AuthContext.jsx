import { createContext, useContext, useEffect, useState } from 'react'

import {
  clearToken,
  fetchMe,
  getToken,
  loginRequest,
  registerRequest,
  setToken,
} from '../lib/api'

/*
  AuthContext — the single source of truth for "who is logged in".

  It holds the current `user` in React state and exposes login / register /
  logout actions. The actual token lives in localStorage (see lib/api.js); this
  context just keeps the UI in sync with it.

  `initializing` matters for the "stay logged in after refresh" requirement:
  on a fresh page load we have a token but no user yet, so we call /auth/me to
  validate it. Until that resolves, ProtectedRoute shows a spinner instead of
  bouncing to /login — otherwise a valid session would flash the login screen
  on every refresh.
*/

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // Start "initializing" only when there's actually a token to validate. With
  // no token there's nothing to check, so we're ready immediately. Computing it
  // here (instead of calling setInitializing inside the effect) avoids a
  // synchronous setState-in-effect, which would trigger a cascading render.
  const [initializing, setInitializing] = useState(() => Boolean(getToken()))

  // On mount: if there's a stored token, confirm it's still valid by loading
  // the current user. A failure (expired/forged token) clears it silently.
  useEffect(() => {
    if (!getToken()) {
      return
    }
    fetchMe()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setInitializing(false))
  }, [])

  async function login(email, password) {
    const { access_token } = await loginRequest(email, password)
    setToken(access_token)
    const me = await fetchMe()
    setUser(me)
    return me
  }

  // Register, then immediately log in so the user lands inside the app rather
  // than being sent back to a login form to retype what they just entered.
  async function register(email, password) {
    await registerRequest(email, password)
    return login(email, password)
  }

  function logout() {
    clearToken()
    setUser(null)
  }

  const value = {
    user,
    initializing,
    isAuthenticated: Boolean(user),
    login,
    register,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// useAuth is intentionally co-located with the provider it belongs to. Doing so
// makes this file export a hook alongside the AuthProvider component, which
// trips Vite's fast-refresh lint rule — a dev-only HMR nicety with no runtime
// impact — so we silence it for this single, well-understood export.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an <AuthProvider>')
  }
  return ctx
}
