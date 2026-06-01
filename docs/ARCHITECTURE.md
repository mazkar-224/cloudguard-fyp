# CloudGuard — Architecture

This document explains every component of CloudGuard and how data flows between
them. It's the technical companion to the [README](../README.md) and the anchor
for the report's Design and Implementation chapters.

---

## 1. High-level overview

CloudGuard is a **four-container application** behind a single HTTPS endpoint:

```
                          ┌──────────────┐
                          │   Browser     │   signed-in user
                          └──────┬────────┘
                                 │ HTTPS (443)
                                 ▼
                    ┌──────────────────────────┐
                    │  Caddy  (reverse proxy)   │  auto Let's Encrypt TLS
                    │  :80 → :443, HSTS,        │  renews certs automatically
                    │  security headers         │
                    └────────────┬──────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │  Frontend container       │  React SPA (Vite build)
                    │  nginx                    │  served as static files;
                    │   • serves SPA            │  /api/* proxied to backend
                    │   • proxies /api/ →       │  (so the browser only ever
                    │     backend:8000          │   talks to one origin)
                    └────────────┬──────────────┘
                                 │ /api/v1/...  (same origin)
                                 ▼
        ┌────────────────────────────────────────────────────┐
        │  Backend container — FastAPI (uvicorn, 1 worker)    │
        │                                                     │
        │  JWT auth (bcrypt) ── guards every data router      │
        │  Routers: auth · costs · alerts · recommendations · │
        │           settings · admin · health                 │
        │                                                     │
        │  APScheduler (in-process, single worker):           │
        │    • cost_sync       every  6h                      │
        │    • resource_scan   every 24h                      │
        │                                                     │
        │  Services:                                          │
        │    AwsCostService    ResourceScanner                │
        │    anomaly_detector  savings_estimator              │
        │    email_service     crypto_service (Fernet)        │
        │    auth_service      credential_service             │
        └───┬─────────────────────────────────┬──────────────┘
            │ SQLAlchemy async (asyncpg)       │ boto3 (run via asyncio.to_thread)
            ▼                                  ▼
   ┌────────────────────┐            ┌──────────────────────────┐
   │  PostgreSQL 16     │            │   AWS APIs                │
   │  (named volume)    │            │   Cost Explorer · STS     │
   │                    │            │   EC2 · CloudWatch        │
   │  users             │            └──────────────────────────┘
   │  aws_credentials   │
   │  aws_accounts      │            ┌──────────────────────────┐
   │  cost_records      │            │  SendGrid (email alerts)  │
   │  alerts            │            └──────────────────────────┘
   │  recommendations   │
   └────────────────────┘
```

All four containers run on one EC2 instance via `docker-compose.prod.yml` on a
private Docker network; only Caddy publishes ports (80/443) to the world.

---

## 2. Components

### Frontend (React SPA + nginx)
- **React 19 + Vite + Tailwind v4**, with **TanStack React Query** for all server
  state (caching, loading/error states, refetch) and **Axios** for HTTP.
- **React Router** drives the screens: public `/login` and `/register`; everything
  else lives inside a `ProtectedRoute` + `Layout` (sidebar + header).
- `lib/api.js` holds the axios client with a **401 interceptor** that bounces the
  user back to login when a token is rejected. `AuthContext` owns login/register/
  logout and the token (stored in `localStorage`).
- In production the build is served by **nginx**, which also **proxies `/api/`** to
  the backend. Because the SPA and the API share one origin, the browser never
  makes a cross-origin request — CORS simply doesn't come into play in prod.

### Backend (FastAPI)
- **FastAPI on uvicorn**, one worker (see design notes). Routers are mounted under
  `/api/v1`. The interactive docs live at **`/api/v1/docs`** (moved under `/api`
  so they're reachable through the nginx proxy).
- **Auth** (`auth_service`, `api/deps.py`): bcrypt password hashing, PyJWT tokens.
  A single `get_current_user` dependency is attached to the costs, alerts,
  recommendations, settings, and admin routers — so **every data endpoint is gated**
  in one place; only `/health` and `/auth/*` are public.

### Background scheduler (APScheduler)
- Runs **in-process** inside the backend, started in FastAPI's lifespan and gated
  by `ENABLE_SCHEDULER`. Two jobs:
  - **`cost_sync`** every 6 hours — pull costs, detect anomalies, send emails.
  - **`resource_scan`** every 24 hours — scan for waste, price it, store
    recommendations.
- Each job is also exposed on demand via `POST /admin/sync` and
  `POST /admin/scan-resources`.

### Domain services
| Service | Responsibility |
|---------|----------------|
| `AwsCostService` | boto3 wrapper around **Cost Explorer**; fetches daily/by-service costs, normalises to exact `Decimal`. |
| `ResourceScanner` | boto3 wrapper around **EC2 + CloudWatch**; runs the five waste finders and a `healthcheck()`. |
| `anomaly_detector` | Pure function: z-score of a day vs. a rolling baseline → severity, with a dollar floor to suppress trivial spikes. No I/O, fully unit-tested. |
| `savings_estimator` | Offline, documented **approximate** pricing table → `{estimated_monthly_usd, basis}`. No live Pricing API call. |
| `email_service` | Sends anomaly emails via **SendGrid** (HTML-escaped); failures are non-fatal. |
| `crypto_service` | **Fernet** encrypt/decrypt for AWS secrets at rest. |
| `auth_service` | Password hashing + JWT create/verify. |
| `credential_service` | Persists / reads / deletes a user's encrypted AWS credentials. |

### Database (PostgreSQL 16)
Accessed with **SQLAlchemy 2.0 async** over the **asyncpg** driver; schema managed
by **Alembic** migrations. Money is stored as `Numeric(12,4)` for exact decimal
precision and only rounded at the API boundary. Data persists in a named Docker
volume.

### Reverse proxy (Caddy)
Terminates TLS with an **auto-provisioned, auto-renewing Let's Encrypt
certificate**, redirects HTTP→HTTPS, and adds security headers (HSTS,
X-Content-Type-Options, X-Frame-Options, Referrer-Policy). The cert is persisted
in a named volume so it survives restarts.

---

## 3. Data model

```
users ──1:1──< aws_credentials          (a user stores one encrypted key pair)

aws_accounts ──1:N──< cost_records       (daily per-service spend)
aws_accounts ──1:N──< alerts             (detected spending spikes)
aws_accounts ──1:N──< recommendations    (waste findings, priced)
```

| Table | Key columns | Notes |
|-------|-------------|-------|
| `users` | `email` (unique), `hashed_password` | bcrypt hash; password never stored in clear. |
| `aws_credentials` | `user_id`, `*_encrypted`, `access_key_last4`, `region` | Both key + secret Fernet-encrypted; only last-4 surfaced. |
| `aws_accounts` | `account_id` (12-digit, unique), `alias` | Resolved via STS; created on first sync. |
| `cost_records` | `date`, `service_name`, `amount_usd` | Upserted (`ON CONFLICT DO UPDATE`) — re-syncing never duplicates. |
| `alerts` | `alert_date`, `scope` (total/service), `service_name`, `amount_usd`, `baseline_mean`, `z_score`, `severity`, `status`, `notified` | Unique per account/date/scope/service (`NULLS NOT DISTINCT`); inserts use `ON CONFLICT DO NOTHING` for idempotency. |
| `recommendations` | `resource_type`, `resource_id`, `region`, `reason`, `estimated_monthly_usd`, `status`, `first_seen_at`, `last_seen_at` | Upserted; `first_seen_at` preserved so "idle for N days" stays accurate. |

---

## 4. Key data flows

### A. Sign-up / login
1. `POST /auth/register` → `auth_service` bcrypt-hashes the password, stores the user.
2. `POST /auth/login` verifies the hash and returns a **JWT** (`Token`).
3. The SPA stores the token and sends it as `Authorization: Bearer …` on every call.
4. `get_current_user` decodes the token on each request; anything invalid/expired → **401**, and the axios interceptor sends the user back to login.

### B. Saving AWS credentials (Settings)
1. `POST /settings/aws-credentials` builds a throwaway `ResourceScanner` and calls
   **`healthcheck()`** to validate the keys against AWS.
2. If validation fails → **400/422**, nothing is stored.
3. On success, `crypto_service` **encrypts** both values, and only the encrypted
   blobs + `access_key_last4` + region are written. Reads return the masked view
   only; the secret is never returned.

### C. Cost sync + anomaly detection (every 6h or `POST /admin/sync`)
1. STS resolves the 12-digit account ID → `aws_accounts` row (created if new).
2. `AwsCostService` fetches the **last 7 days** from Cost Explorer
   (`boto3` calls run in `asyncio.to_thread` so the event loop isn't blocked).
3. Rows are **upserted** into `cost_records`.
4. `anomaly_detector` runs over the **trailing 21 days**, for the **account total**
   and the **top services**, comparing each candidate day to a rolling baseline.
5. Spikes are inserted into `alerts` (idempotent), then `email_service` emails any
   un-notified, recent alerts and flips their `notified` flag on success.

### D. Resource scan + recommendations (every 24h or `POST /admin/scan-resources`)
1. `ResourceScanner.scan_all()` runs the five waste finders (unattached EBS,
   unassociated EIP, stopped instances, old snapshots, idle running instances via
   CloudWatch CPU).
2. `savings_estimator` prices each finding (approximate monthly USD).
3. Findings are **upserted** into `recommendations` — refreshing the estimate and
   `last_seen_at` while preserving `first_seen_at`.

### E. Reading the dashboard
Browser → Caddy (TLS) → nginx (serves SPA, proxies `/api/`) → FastAPI →
**PostgreSQL first**. The cost endpoints fall back to a **live AWS call** only when
the database is empty, so normal page loads are fast and don't hit AWS.

---

## 5. Design decisions (and their trade-offs)

- **Async end-to-end, but boto3 in a thread.** FastAPI + SQLAlchemy async keep the
  app non-blocking; boto3 is synchronous, so AWS calls are wrapped in
  `asyncio.to_thread` rather than blocking the event loop.
- **Idempotent upserts everywhere.** Costs, alerts, and recommendations all use
  `ON CONFLICT` so re-running a sync/scan never creates duplicates — important
  because the same data is fetched repeatedly.
- **Single uvicorn worker.** The scheduler runs *in-process*; with multiple workers
  each would start its own scheduler and fire every job N times. One worker keeps
  the scheduler authoritative. To scale horizontally you'd set
  `ENABLE_SCHEDULER=false` on extra replicas and run it on exactly one.
- **Same-origin in production.** Serving the SPA and proxying `/api` through one
  nginx origin means no CORS in prod; the CORS middleware exists only for local
  dev (Vite on a different port).
- **Secrets encrypted at rest, validated before save.** AWS keys are never stored
  unless they actually work, never stored in clear, and never returned.
- **Exact money.** `Numeric(12,4)` avoids floating-point drift; rounding happens
  only when serialising to the API.

### Known limitation / future work
The **scheduled jobs currently use the single set of AWS credentials from the
environment** (`settings.aws_access_key_id`), not each user's stored, encrypted
credentials. The per-user credential store (Settings page) is fully implemented —
validated, encrypted, masked — but wiring the schedulers to iterate per user and
use each user's decrypted keys is the natural next step toward true multi-tenant
operation. This is called out in the report's Evaluation / Future Work sections.

---

## 6. Drawing the diagram in Excalidraw

For the report, redraw Section 1 as a clean diagram. Suggested layout
(top → bottom), so it reads as the request path:

1. **Browser** (rounded rectangle, top). Arrow down labelled **"HTTPS"**.
2. **EC2 instance** — draw one large dashed container box labelled
   *"AWS EC2 (Ubuntu) · Docker Compose"* and put the next four boxes **inside** it:
   - **Caddy** (reverse proxy) — note *"auto Let's Encrypt TLS, :80→:443, HSTS"*.
     Arrow down labelled **"proxies all traffic"**.
   - **Frontend — nginx + React SPA** — note *"serves UI, proxies /api"*.
     Arrow down labelled **"/api/v1 (same origin)"**.
   - **Backend — FastAPI (uvicorn, 1 worker)** — inside it list three stacked
     sub-boxes: *"JWT auth → routers"*, *"APScheduler: cost_sync 6h · resource_scan 24h"*,
     and *"Services: AwsCostService, ResourceScanner, anomaly_detector,
     savings_estimator, email_service, crypto, auth"*.
   - **PostgreSQL 16** (cylinder) — note *"named volume"* and list the six tables.
3. From the **Backend** box, draw **two arrows leaving the EC2 box to the right**:
   - one labelled **"boto3 (asyncio.to_thread)"** → a box **"AWS APIs: Cost
     Explorer · STS · EC2 · CloudWatch"**.
   - one labelled **"HTTPS"** → a box **"SendGrid (email)"**.
4. From **Backend** down to **PostgreSQL**, label the arrow
   **"SQLAlchemy async (asyncpg)"**.
5. Colour suggestion: blue for app containers, green for the database, grey for
   external AWS/SendGrid, and a thin lock icon on the Browser→Caddy arrow to
   signal TLS.

Keep arrows one-directional along the request path; that single diagram is enough
to anchor the whole defense.
