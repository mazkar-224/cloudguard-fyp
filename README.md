# CloudGuard

> AWS cost monitoring and anomaly detection — FastAPI · PostgreSQL · React · Tailwind

CloudGuard connects to your AWS account and pulls spending data from Cost Explorer every 6 hours. Costs are stored in PostgreSQL and served through a REST API to a React dashboard that shows daily spend trends, per-service breakdowns, and period-over-period comparisons — all in one view.

This is a final-year capstone project (BSCS). The goal is a fully functional, self-hosted alternative to the AWS billing console for teams that want a single dashboard without navigating the AWS UI.

---

## Screenshots

| Light mode | Dark mode |
|------------|-----------|
| ![Dashboard light](docs/screenshots/dashboard-light.png) | ![Dashboard dark](docs/screenshots/dashboard-dark.png) |

| Charts with real data | Empty state |
|-----------------------|-------------|
| ![Charts](docs/screenshots/charts-detail.png) | ![Empty state](docs/screenshots/empty-state.png) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Dashboard                             │
│              Vite · Tailwind v4 · Recharts · React Query        │
│                    http://localhost:5173                         │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP  /api/v1/  (Vite proxy)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI  /api/v1/                          │
│                    http://localhost:8000                         │
│                                                                 │
│   GET  /health          GET  /costs/daily                       │
│   GET  /costs/summary   GET  /costs/by-service                  │
│   GET  /alerts          GET  /alerts/count                      │
│   PATCH /alerts/{id}    ← acknowledge                           │
│   POST /admin/sync      ← manual trigger                        │
│                                                                 │
│   APScheduler ──► run_sync_job()  every 6 hours                 │
│         │                   │                                   │
│         ▼                   ▼                                   │
│   AwsCostService      sync_cost_data()                          │
│   (boto3 wrapper)     1. upsert → cost_records                  │
│                       2. detect_anomalies() → alerts            │
└──────────┬───────────────────────┬──────────────────────────────┘
           │  asyncio.to_thread    │  SQLAlchemy async (asyncpg)
           ▼                       ▼
┌──────────────────┐   ┌───────────────────────────────┐
│   AWS Cost       │   │   PostgreSQL  (port 5433)     │
│   Explorer API   │   │                               │
│                  │   │   aws_accounts                │
│   STS (account   │   │   cost_records                │
│   ID lookup)     │   │   alerts  ← Phase 4           │
│                  │   │     ├─ scope (total/service)  │
│                  │   │     ├─ z_score, severity      │
└──────────────────┘   │     └─ status, notified       │
                       └───────────────────────────────┘
```

**Data flow:** Every 6 hours (or on `POST /admin/sync`) the sync job calls AWS Cost Explorer, upserts the last 7 days into PostgreSQL, then runs anomaly detection on the trailing 21 days — flagging account-level spikes (`scope='total'`) and per-service spikes (`scope='service'`) using a z-score against a 14-day rolling mean. Detected anomalies persist as `alerts` rows and, when SendGrid is configured, trigger an email notification. The Alerts page lists, filters, and acknowledges them. All dashboard reads hit PostgreSQL first — AWS is only called when the database is empty.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite, Tailwind CSS v4, Recharts, TanStack React Query v5, Axios |
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 async, Alembic, APScheduler 3 |
| Database | PostgreSQL 16 (Docker), asyncpg driver |
| AWS | Boto3 · Cost Explorer API · STS |
| Dev tooling | Docker Compose, pgAdmin, ESLint, Prettier, Pytest |

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Desktop | any | Runs PostgreSQL + pgAdmin |
| Python | 3.12+ | Backend runtime |
| Node.js | 18+ | Frontend dev server |
| AWS account | — | Real cost data (optional for tests) |

---

## One-command startup

After completing the first-run setup below, start the entire stack with a single command:

**Linux / macOS / WSL:**
```bash
bash scripts/dev.sh
```

**Windows (Command Prompt):**
```bat
scripts\dev.bat
```

This starts PostgreSQL, waits for the database to be ready, then launches the FastAPI backend and Vite frontend. Press `Ctrl+C` to stop everything.

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |

---

## First-run setup

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd cloudguard
```

### 2. Configure environment variables

```bash
# Root .env (database credentials for Docker Compose)
cp .env.example .env

# Backend .env (AWS credentials)
cp backend/.env.example backend/.env
```

Open `backend/.env` and set your AWS credentials:

```
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_DEFAULT_REGION=us-east-1
```

> **Required IAM permission:** `ce:GetCostAndUsage` on `*`

### 3. Start PostgreSQL (Docker)

```bash
docker compose up -d
```

### 4. Set up the backend virtualenv

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 6. Install frontend dependencies

```bash
cd frontend
npm install
```

You only need steps 3–6 once. After that, use `scripts/dev.sh` to start everything.

---

## API reference

### Health

```
GET /api/v1/health
```

Returns `{ "status": "ok", "version": "0.2.0", "environment": "development" }`

### Cost data

```
GET /api/v1/costs/daily?days=30
GET /api/v1/costs/by-service?start_date=2026-05-01&end_date=2026-05-20
GET /api/v1/costs/summary?days=30
```

All three read from PostgreSQL first. If the database is empty they fall back to a live AWS call automatically.

### Alerts

```
GET   /api/v1/alerts?status=new&severity=high&days=30&limit=50&offset=0
GET   /api/v1/alerts/count?days=30
PATCH /api/v1/alerts/{id}            ← mark acknowledged
```

`GET /alerts` lists anomaly alerts newest-first with optional `status` / `severity` filters, a `days` window, and pagination. `GET /alerts/count` returns counts grouped by status and severity over the same window (drives the sidebar badge). `PATCH /alerts/{id}` flips a `new` alert to `acknowledged`.

### Admin

```
POST /api/v1/admin/sync
```

Triggers an immediate sync from AWS Cost Explorer, then runs anomaly detection on the trailing 21 days. Use during a demo to populate the database and see the dashboard update live. Returns `{ rows_upserted, new_alerts_created, duration_seconds }`.

Full interactive docs: **http://localhost:8000/docs**

---

## Running tests

Tests run against a separate `cloudguard_test` database — your real data is never touched.

```bash
cd backend

# Run all tests
venv/bin/python3 -m pytest tests/ -v

# Run with coverage report
venv/bin/python3 -m pytest --cov=app --cov-report=term-missing tests/
```

Current test count: **52 tests** (28 in Phase 3, +24 across Phase 4)

| File | What it tests |
|------|--------------|
| `test_health.py` | `/health` returns 200 with correct shape |
| `test_costs.py` | All three cost endpoints with seeded DB data |
| `test_admin_sync.py` | Sync endpoint — 200, correct count, idempotency |
| `test_aws_cost.py` | `AwsCostService` unit tests — error handling, parsing |
| `test_anomaly_detector.py` | Pure z-score algorithm — spike, normal, zero variance, severity bands, dollar floor, empty input |
| `test_cost_sync.py` | End-to-end: seeded baseline + spike → Alert; idempotent re-run; extreme z-score is clamped not overflowed |
| `test_email_service.py` | SendGrid alert email — payload, HTML escaping, config-missing + failure handling (mocked) |
| `test_alerts_api.py` | `/alerts` list filters + pagination, `/alerts/count` grouping + days window, `PATCH` acknowledge + 404 |
| `test_e2e_spike_to_alert.py` | Full pipeline: spike → detection → alert → email sent → visible via API (AWS + SendGrid mocked) |

---

## Project structure

```
cloudguard/
├── scripts/
│   ├── dev.sh               # One-command startup (Linux/macOS/WSL)
│   └── dev.bat              # One-command startup (Windows)
├── docs/
│   ├── anomaly-detection.md # How the z-score detector works, limits, demo script
│   └── screenshots/         # Dashboard screenshots for the report
├── frontend/
│   ├── src/
│   │   ├── components/      # Layout, StatCard, Sidebar, charts, EmptyState, ErrorBoundary
│   │   ├── hooks/           # useCostSummary, useDailyCosts, useSync, useAlerts, useAlertCounts, useAcknowledgeAlert
│   │   ├── lib/             # api.js (all backend calls via axios)
│   │   └── pages/           # DashboardPage, AlertsPage, SettingsPage
│   ├── index.html
│   └── vite.config.js       # Proxy /api → localhost:8000
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers (health, costs, admin, alerts)
│   │   ├── db/              # SQLAlchemy engine + session
│   │   ├── jobs/            # APScheduler background sync + detection
│   │   ├── models/          # ORM models (AwsAccount, CostRecord, Alert)
│   │   ├── schemas/         # Pydantic response models
│   │   ├── services/        # AwsCostService, anomaly_detector, email_service
│   │   ├── config.py        # Settings loaded from .env
│   │   └── main.py          # FastAPI app + lifespan
│   ├── alembic/             # Database migrations
│   ├── scripts/             # inject_spike.py — synthetic spike for live demos
│   ├── tests/               # Pytest test suite (52 tests)
│   ├── requirements.txt
│   └── .env                 # Local secrets (gitignored)
└── docker-compose.yml
```

---

## Phase roadmap

- [x] **Phase 1** — Project setup
  - Docker Compose with PostgreSQL 16 + pgAdmin
  - FastAPI app skeleton with CORS, settings via Pydantic
  - Alembic migration creating `aws_accounts` + `cost_records` tables
- [x] **Phase 2** — Backend API (28 tests passing)
  - `AwsCostService` boto3 wrapper around Cost Explorer with async-safe `asyncio.to_thread()`
  - 5 REST endpoints: `/health`, `/costs/daily`, `/costs/by-service`, `/costs/summary`, `/admin/sync`
  - APScheduler background job — every 6 hours, upserts via PostgreSQL `ON CONFLICT DO UPDATE`
  - STS account-ID lookup with graceful fallback when blocked
  - `Numeric(12,4)` for money (exact decimal precision, rounded only at API boundary)
- [x] **Phase 3** — React dashboard
  - **3.1** Vite + Tailwind v4 (CSS-first `@theme`) scaffold, ESLint, Prettier, `/api` proxy
  - **3.2** Axios + TanStack React Query v5 with global error handler, devtools panel
  - **3.3** App shell — sticky header + sidebar, React Router nested routes, `lucide-react` icons
  - **3.4** 4 summary cards (30d / 7d / yesterday / week-over-week %) with skeleton + error states
  - **3.5** Daily costs line chart (7d/30d/90d selector) + service breakdown donut (top 5 + Other)
  - **3.6** Dark mode toggle with FOUC prevention, `sonner` toasts, empty state, React error boundary
  - **3.7** `useSync` mutation, one-command startup scripts (`dev.sh` / `dev.bat`), demo screenshots
- [x] **Phase 4** — Anomaly detection (52 tests passing)
  - **4.1** Pure z-score detection algorithm with severity bands + dollar floor + 7 unit tests
  - **4.2** `alerts` database table with `NULLS NOT DISTINCT` unique constraint (one alert per account/date/scope/service)
  - **4.3** Detection wired into sync (account total + per-service top 5), idempotent `ON CONFLICT DO NOTHING` inserts
  - **4.4** SendGrid email notifications — HTML-escaped body, `notified` flag flip on success, non-fatal failures, recency cutoff
  - **4.5** Alerts API — `GET /alerts` (status/severity filters, days window, pagination), `GET /alerts/count`, `PATCH /alerts/{id}`
  - **4.6** Alerts UI page — filterable list, severity badges, acknowledge mutation, sidebar new-alert count badge
  - **4.7** Demo readiness — `inject_spike.py` synthetic-spike injector, end-to-end pipeline test, `docs/anomaly-detection.md`
- [ ] **Phase 5** — Deployment (Docker, CI/CD)
