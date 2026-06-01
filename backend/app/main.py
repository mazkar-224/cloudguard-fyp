from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import v1_router
from app.api.v1.health import APP_VERSION
from app.config import settings
from app.jobs.cost_sync import run_sync_job
from app.jobs.resource_scan import run_scan_job

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan replaces the old @app.on_event("startup") / ("shutdown") pattern.
    Everything before `yield` runs on startup; everything after runs on shutdown.

    Why lifespan instead of on_event?
      FastAPI deprecated on_event. Lifespan is the modern, recommended way
      and it handles errors more cleanly (shutdown still runs even if startup fails).

    The scheduler is gated behind settings.enable_scheduler. It runs in-process,
    so with multiple uvicorn workers it would start once per worker; disable it on
    all but one instance (ENABLE_SCHEDULER=false) to avoid firing jobs N times.
    """
    if settings.enable_scheduler:
        scheduler.add_job(
            run_sync_job,
            trigger="interval",
            hours=6,
            id="cost_sync",
            replace_existing=True,
        )
        # Resource scans are heavier and change slowly, so daily is plenty.
        scheduler.add_job(
            run_scan_job,
            trigger="interval",
            hours=24,
            id="resource_scan",
            replace_existing=True,
        )
        scheduler.start()

    yield

    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="CloudGuard API",
    version=APP_VERSION,
    description="""
## CloudGuard — AWS Cost Monitoring & Anomaly Detection

CloudGuard gives you a real-time view of your AWS spending without opening
the AWS Console. It pulls data from **AWS Cost Explorer**, stores it in
PostgreSQL, and serves it through this API to a React dashboard.

### How data flows
1. Every **6 hours** APScheduler calls `POST /api/v1/admin/sync` internally.
2. The sync job fetches the last 7 days from AWS and **upserts** them into
   the `cost_records` table — re-running is safe, no duplicates are created.
3. Cost endpoints read from **PostgreSQL first** (fast, free).
   If the database is empty they fall back to a **live AWS call** automatically.

### Running a live demo
Hit `POST /api/v1/admin/sync` in Swagger UI, then refresh your dashboard charts.
The `rows_upserted` and `duration_seconds` fields in the response confirm the sync worked.

### Error codes
| Code | Meaning |
|------|---------|
| 400  | Invalid or missing AWS credentials |
| 403  | IAM policy missing `ce:GetCostAndUsage` permission |
| 422  | Bad query parameter (e.g. `days=0`) |
| 502  | Unexpected AWS error — check CloudWatch or retry |
""",
    contact={
        "name": "Muhammad Azkar",
        "email": "mgtstore29@gmail.com",
    },
    license_info={"name": "MIT"},
    openapi_tags=[
        {
            "name": "health",
            "description": "Liveness check — confirms the API is reachable and returns the current version.",
        },
        {
            "name": "costs",
            "description": (
                "AWS cost data. Reads from PostgreSQL when available, "
                "falls back to a live AWS Cost Explorer call when the DB is empty."
            ),
        },
        {
            "name": "admin",
            "description": (
                "Operational endpoints. Trigger an on-demand sync or verify "
                "that credentials and IAM permissions are working."
            ),
        },
    ],
    lifespan=lifespan,
)

# Local dev origins are always allowed; production extras come from
# CORS_ALLOW_ORIGINS (comma-separated). In the default same-origin deployment
# (SPA served by nginx, which proxies /api) no cross-origin call is made, so the
# extras list is typically empty.
_cors_origins = ["http://localhost:3000", "http://localhost:5173"] + [
    origin.strip()
    for origin in settings.cors_allow_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
