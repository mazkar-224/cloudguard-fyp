# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: install production dependencies into an isolated venv.
# Build tools (gcc etc.) live ONLY in this stage, so they never reach the final
# image. We copy just the resulting /opt/venv forward.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential covers any dependency that needs to compile from source.
# Most of our wheels are prebuilt, but this keeps the build robust.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Self-contained virtualenv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy ONLY requirements first so this layer caches until deps actually change —
# editing app code won't trigger a full reinstall.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: slim image with just the venv + app code, run as non-root.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Dedicated unprivileged user — never run the app as root.
RUN groupadd --system app \
    && useradd --system --uid 1001 --gid app --no-create-home appuser

WORKDIR /app

# Bring the prebuilt venv over from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy the application source (see .dockerignore for what's excluded).
# alembic/ + alembic.ini are included so migrations can run inside this image.
COPY --chown=appuser:app . .

USER appuser

EXPOSE 8000

# Liveness probe using the stdlib (no curl in the slim image). Hits the public
# health route; a non-200 / connection error makes the container unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status==200 else sys.exit(1)"

# Single worker on purpose: the APScheduler background jobs run in-process, so
# every extra worker starts its own scheduler and fires each job again. One
# worker keeps the scheduler authoritative (jobs run exactly once) and is ample
# for this workload. Scale out behind a load balancer with ENABLE_SCHEDULER=false
# on the extra replicas if higher throughput is ever needed (see app/config.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
