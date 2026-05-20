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
