@echo off
REM dev.bat — start the full CloudGuard stack on Windows.
REM
REM Usage (run from the project root):
REM   scripts\dev.bat
REM
REM Requirements: Docker Desktop running, Python venv created, npm installed.

echo [dev] Starting CloudGuard development environment...
echo.

REM ── 1. PostgreSQL ────────────────────────────────────────────────────────────
echo [dev] Starting PostgreSQL (Docker Compose)...
docker compose up -d
if errorlevel 1 (
  echo [dev] ERROR: Docker Compose failed. Is Docker Desktop running?
  pause
  exit /b 1
)
echo [dev] PostgreSQL started.
echo.

REM ── Brief wait for Postgres to be ready ──────────────────────────────────────
echo [dev] Waiting for database to be ready...
timeout /t 5 /nobreak >nul

REM ── 2. Backend ───────────────────────────────────────────────────────────────
echo [dev] Starting FastAPI backend in a new window...
start "CloudGuard Backend" cmd /k ^
  "cd /d %~dp0..\backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

REM ── 3. Frontend ──────────────────────────────────────────────────────────────
echo [dev] Starting Vite frontend in a new window...
start "CloudGuard Frontend" cmd /k ^
  "cd /d %~dp0..\frontend && npm run dev"

echo.
echo [dev] All services are starting.
echo [dev]   Dashboard  -^>  http://localhost:5173
echo [dev]   API        -^>  http://localhost:8000
echo [dev]   Swagger    -^>  http://localhost:8000/docs
echo [dev]   pgAdmin    -^>  http://localhost:5050
echo.
echo [dev] Close the Backend and Frontend windows to stop those services.
echo [dev] Run "docker compose stop" to stop PostgreSQL.
echo.
pause
