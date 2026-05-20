#!/usr/bin/env bash
# dev.sh — start the full CloudGuard stack with one command.
#
# Usage:
#   bash scripts/dev.sh
#
# What it does:
#   1. Starts PostgreSQL via Docker Compose
#   2. Waits until the database is accepting connections
#   3. Starts the FastAPI backend (with auto-reload)
#   4. Starts the Vite frontend dev server
#   5. Ctrl+C stops everything cleanly

set -e

# ── Resolve project root regardless of where the script is called from ────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log()     { echo -e "${YELLOW}[dev]${NC}      $1"; }
log_ok()  { echo -e "${YELLOW}[dev]${NC}      ${GREEN}$1${NC}"; }

# ── Load root .env so we get POSTGRES_USER / POSTGRES_DB for the health check ─
if [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi
DB_USER="${POSTGRES_USER:-cloudguard}"
DB_NAME="${POSTGRES_DB:-cloudguard}"

# ── 1. Docker Compose ─────────────────────────────────────────────────────────
log "Starting PostgreSQL (Docker Compose)..."
docker compose -f "$ROOT/docker-compose.yml" up -d

# Poll until the database is ready — avoids "connection refused" on cold starts
log "Waiting for PostgreSQL to accept connections..."
until docker compose -f "$ROOT/docker-compose.yml" exec -T db \
      pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
  sleep 1
done
log_ok "PostgreSQL is ready ✓"

# ── 2. Backend ────────────────────────────────────────────────────────────────
# Runs inside the virtualenv; output lines are prefixed with [backend]
log "Starting FastAPI backend on http://localhost:8000 ..."
(
  cd "$ROOT/backend"
  source venv/bin/activate
  uvicorn app.main:app --reload --port 8000 2>&1 \
    | sed "s/^/$(printf "${GREEN}[backend]${NC} ")/"
) &
BACKEND_PID=$!

# ── 3. Frontend ───────────────────────────────────────────────────────────────
log "Starting Vite frontend on http://localhost:5173 ..."
(
  cd "$ROOT/frontend"
  npm run dev 2>&1 \
    | sed "s/^/$(printf "${BLUE}[frontend]${NC} ")/"
) &
FRONTEND_PID=$!

# ── URLs ──────────────────────────────────────────────────────────────────────
echo ""
log_ok "Stack is up:"
log    "  Dashboard  →  http://localhost:5173"
log    "  API        →  http://localhost:8000"
log    "  Swagger    →  http://localhost:8000/docs"
log    "  pgAdmin    →  http://localhost:5050"
echo ""
log    "Press Ctrl+C to stop everything."
echo ""

# ── Graceful shutdown ─────────────────────────────────────────────────────────
cleanup() {
  echo ""
  log "Shutting down..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  docker compose -f "$ROOT/docker-compose.yml" stop
  log_ok "All services stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

# Keep the script alive until Ctrl+C
wait
