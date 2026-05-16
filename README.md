# CloudGuard

AWS cost monitoring and anomaly detection — FastAPI + PostgreSQL + React (Tailwind).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         React Dashboard                         │
│              (Phase 3 — charts, Tailwind, Vite)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP  (localhost:3000 → 8000)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI  /api/v1/                          │
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

**Data flow:** Every 6 hours (or on `POST /admin/sync`) the sync job calls AWS Cost Explorer,
upserts the last 7 days into PostgreSQL, and returns. All dashboard reads hit PostgreSQL first —
AWS is only called when the database is empty.

---

## What it does

- Pulls the last 7 days of AWS spending from **Cost Explorer** every 6 hours
- Stores cost data in **PostgreSQL** so repeated reads are instant and free
- Serves three REST endpoints: daily costs, per-service totals, and a summary
- Provides a manual sync trigger (`POST /admin/sync`) for live demos

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Backend runtime |
| Docker Desktop | any | Runs PostgreSQL |
| AWS account | — | Real cost data (optional for tests) |

---

## Quick start

### 1. Start PostgreSQL

```bash
cd /path/to/cloudguard
docker compose up -d
```

This starts two containers:
- `cloudguard_db` — main database on port **5433**
- `cloudguard_test_db` — test database on port **5433** (same host, separate DB)

Verify they're running:
```bash
docker compose ps
```

### 2. Set up the backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
# Copy the example file and fill in your AWS credentials
cp .env.example .env
```

Open `backend/.env` and set:

```
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
```

> **Required IAM permission:** `ce:GetCostAndUsage` on `*`

### 4. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start the API

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API is now running at **http://localhost:8000**

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger UI — interactive API docs |
| http://localhost:8000/api/v1/health | Health check |

---

## Endpoints

### Health

```
GET /api/v1/health
```

Returns `{ "status": "ok", "version": "0.2.0", "environment": "development" }`

### Cost data

```
GET /api/v1/costs/daily?days=30
GET /api/v1/costs/by-service?start_date=2026-05-01&end_date=2026-05-17
GET /api/v1/costs/summary?days=30
```

All three read from PostgreSQL first. If the database is empty they fall back to a live AWS call automatically.

### Admin

```
POST /api/v1/admin/sync
```

Triggers an immediate sync from AWS Cost Explorer. Use this to populate the database on first run or during a live demo. Returns `rows_upserted` and `duration_seconds`.

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

### What the tests cover

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
│   ├── tests/               # Pytest test suite
│   ├── requirements.txt
│   └── .env                 # Local secrets (gitignored)
└── docker-compose.yml
```

---

## Phase roadmap

- [x] **Phase 1** — Project setup (Docker, git, folder structure)
- [x] **Phase 2** — Backend API (FastAPI, PostgreSQL, AWS integration, tests)
- [ ] **Phase 3** — React dashboard (charts, Tailwind UI)
- [ ] **Phase 4** — Anomaly detection
- [ ] **Phase 5** — Deployment (Docker, CI/CD)
