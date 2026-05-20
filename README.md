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
│   POST /admin/sync      ← manual trigger                        │
│                                                                 │
│   APScheduler ──► run_sync_job()  every 6 hours                 │
│         │                   │                                   │
│         ▼                   ▼                                   │
│   AwsCostService      sync_cost_data()                          │
│   (boto3 wrapper)     upsert → cost_records                     │
└──────────┬───────────────────────┬──────────────────────────────┘
           │  asyncio.to_thread    │  SQLAlchemy async (asyncpg)
           ▼                       ▼
┌──────────────────┐   ┌───────────────────────────────┐
│   AWS Cost       │   │   PostgreSQL  (port 5433)     │
│   Explorer API   │   │                               │
│                  │   │   aws_accounts                │
│   STS (account   │   │   cost_records                │
│   ID lookup)     │   │     ├─ date                   │
│                  │   │     ├─ service_name            │
└──────────────────┘   │     └─ amount_usd Numeric(12,4)│
                       └───────────────────────────────┘
```

**Data flow:** Every 6 hours (or on `POST /admin/sync`) the sync job calls AWS Cost Explorer, upserts the last 7 days into PostgreSQL, and returns. All dashboard reads hit PostgreSQL first — AWS is only called when the database is empty.

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

### Admin

```
POST /api/v1/admin/sync
```

Triggers an immediate sync from AWS Cost Explorer. Use during a demo to populate the database and see the dashboard update live. Returns `{ rows_upserted, duration_seconds }`.

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

Current coverage: **72%** (threshold: 70%)

| File | What it tests |
|------|--------------|
| `test_health.py` | `/health` returns 200 with correct shape |
| `test_costs.py` | All three cost endpoints with seeded DB data |
| `test_admin_sync.py` | Sync endpoint — 200, correct count, idempotency |
| `test_aws_cost.py` | `AwsCostService` unit tests — error handling, parsing |

---

## Project structure

```
cloudguard/
├── scripts/
│   ├── dev.sh               # One-command startup (Linux/macOS/WSL)
│   └── dev.bat              # One-command startup (Windows)
├── docs/
│   └── screenshots/         # Dashboard screenshots for the report
├── frontend/
│   ├── src/
│   │   ├── components/      # Layout, StatCard, charts, EmptyState, ErrorBoundary
│   │   ├── hooks/           # useCostSummary, useDailyCosts, useCostsByService, useSync
│   │   ├── lib/             # api.js (all backend calls via axios)
│   │   └── pages/           # DashboardPage, AlertsPage, SettingsPage
│   ├── index.html
│   └── vite.config.js       # Proxy /api → localhost:8000
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers (health, costs, admin)
│   │   ├── db/              # SQLAlchemy engine + session
│   │   ├── jobs/            # APScheduler background sync
│   │   ├── models/          # ORM models (AwsAccount, CostRecord)
│   │   ├── schemas/         # Pydantic response models
│   │   ├── services/        # AwsCostService (wraps boto3)
│   │   ├── config.py        # Settings loaded from .env
│   │   └── main.py          # FastAPI app + lifespan
│   ├── alembic/             # Database migrations
│   ├── tests/               # Pytest test suite (28 tests)
│   ├── requirements.txt
│   └── .env                 # Local secrets (gitignored)
└── docker-compose.yml
```

---

## Phase roadmap

- [x] **Phase 1** — Project setup (Docker, git, folder structure)
- [x] **Phase 2** — Backend API (FastAPI, PostgreSQL, AWS integration, 28 tests)
- [x] **Phase 3** — React dashboard (Recharts charts, Tailwind v4, dark mode, toast notifications)
- [ ] **Phase 4** — Anomaly detection
- [ ] **Phase 5** — Deployment (Docker, CI/CD)
