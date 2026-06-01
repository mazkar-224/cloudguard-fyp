/**
 * API client for the CloudGuard backend.
 *
 * axios is used instead of raw fetch because it:
 *   - automatically throws on non-2xx responses (no manual `if (!res.ok)` checks)
 *   - parses JSON for you (res.data instead of await res.json())
 *   - gives cleaner error messages with the response body attached
 *
 * The Vite dev server proxy (vite.config.js) forwards every /api/* request
 * to http://localhost:8000, so we never hard-code the backend URL here.
 */

import axios from 'axios'

// One shared axios instance — base URL points at the proxy path
const api = axios.create({
  baseURL: '/api/v1',
})

// ── Auth token storage ──────────────────────────────────────────────────────
// The JWT lives in localStorage so a page refresh keeps you logged in. It's a
// single source of truth: the request interceptor below reads it, and the
// AuthContext mirrors it into React state for the UI.

const TOKEN_KEY = 'cloudguard_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

// Request interceptor — this is the stub from Phase 3.2 finally earning its
// place. Every outgoing request gets `Authorization: Bearer <token>` attached
// automatically, so individual API calls never have to think about auth.
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — if the server ever rejects us with 401 (expired or
// invalid token), drop the dead token and bounce to the login screen. We skip
// this for the /auth/* calls themselves so a wrong password on the login form
// shows an inline error instead of triggering a redirect loop.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const isAuthCall = url.startsWith('/auth/')

    if (status === 401 && !isAuthCall) {
      clearToken()
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  },
)

// ── Auth endpoints ────────────────────────────────────────────────────────────

// POST /auth/register — create an account, returns the new user
export function registerRequest(email, password) {
  return api.post('/auth/register', { email, password }).then((r) => r.data)
}

// POST /auth/login — exchange credentials for { access_token, token_type }
export function loginRequest(email, password) {
  return api.post('/auth/login', { email, password }).then((r) => r.data)
}

// GET /auth/me — the currently logged-in user (validates a stored token)
export function fetchMe() {
  return api.get('/auth/me').then((r) => r.data)
}

// GET /health — confirm the backend is up
export function fetchHealth() {
  return api.get('/health').then(r => r.data)
}

// GET /costs/summary — total spend, top service, days covered
export function fetchSummary(days = 30) {
  return api.get(`/costs/summary?days=${days}`).then(r => r.data)
}

// GET /costs/daily — per-day per-service cost rows
export function fetchDailyCosts(days = 30) {
  return api.get(`/costs/daily?days=${days}`).then(r => r.data)
}

// GET /costs/by-service — totals grouped by service, sorted by cost desc
export function fetchByService(startDate, endDate) {
  return api.get(`/costs/by-service?start_date=${startDate}&end_date=${endDate}`).then(r => r.data)
}

// POST /admin/sync — trigger a manual AWS → DB sync
export function triggerSync() {
  return api.post('/admin/sync').then(r => r.data)
}

// GET /alerts — list anomaly alerts with optional filters + pagination.
// 'all' / undefined filters are omitted so the backend returns everything.
export function fetchAlerts({ status, severity, days = 30, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (status && status !== 'all') params.set('status', status)
  if (severity && severity !== 'all') params.set('severity', severity)
  params.set('days', days)
  params.set('limit', limit)
  params.set('offset', offset)
  return api.get(`/alerts?${params.toString()}`).then(r => r.data)
}

// GET /alerts/count — counts grouped by status and severity (drives the badge)
export function fetchAlertCounts(days = 30) {
  return api.get(`/alerts/count?days=${days}`).then(r => r.data)
}

// PATCH /alerts/{id} — mark an alert acknowledged, returns the updated alert
export function acknowledgeAlert(id) {
  return api.patch(`/alerts/${id}`).then(r => r.data)
}

// GET /recommendations — list cost-saving recommendations, sorted by savings.
// 'all'/empty filters are omitted so the backend applies its defaults.
export function fetchRecommendations({ resourceType, status = 'open', limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (resourceType && resourceType !== 'all') params.set('resource_type', resourceType)
  if (status) params.set('status', status)
  params.set('limit', limit)
  params.set('offset', offset)
  return api.get(`/recommendations?${params.toString()}`).then(r => r.data)
}

// GET /recommendations/summary — total monthly savings + open count + breakdown
export function fetchRecommendationsSummary() {
  return api.get('/recommendations/summary').then(r => r.data)
}

// PATCH /recommendations/{id} — set status to 'dismissed' or 'resolved'
export function updateRecommendation(id, status) {
  return api.patch(`/recommendations/${id}`, { status }).then(r => r.data)
}

// POST /admin/scan-resources — trigger a live AWS resource scan
export function triggerResourceScan() {
  return api.post('/admin/scan-resources').then(r => r.data)
}

// ── Settings: per-user AWS credentials ─────────────────────────────────────────
// The secret is write-only from the API's side: we send it on save, but GET only
// ever returns a masked last-4 + region. So the frontend never holds the secret
// after submitting the form.

// GET /settings/aws-credentials — masked saved credential, or null if none saved
export function fetchAwsCredentials() {
  return api.get('/settings/aws-credentials').then(r => r.data)
}

// POST /settings/aws-credentials — validate (via healthcheck) + encrypt + save
export function saveAwsCredentials({ accessKeyId, secretAccessKey, region }) {
  return api
    .post('/settings/aws-credentials', {
      access_key_id: accessKeyId,
      secret_access_key: secretAccessKey,
      region,
    })
    .then(r => r.data)
}

// DELETE /settings/aws-credentials — remove the saved credential
export function deleteAwsCredentials() {
  return api.delete('/settings/aws-credentials').then(r => r.data)
}

// POST /settings/test-connection — check credentials without saving → {ok, detail}
export function testAwsConnection({ accessKeyId, secretAccessKey, region }) {
  return api
    .post('/settings/test-connection', {
      access_key_id: accessKeyId,
      secret_access_key: secretAccessKey,
      region,
    })
    .then(r => r.data)
}
