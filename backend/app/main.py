from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import v1_router

app = FastAPI(
    title="CloudGuard API",
    version="0.1.0",
    description="AWS cost monitoring and anomaly detection",
)

# CORS — allows the React frontend to call this backend from the browser.
# Without this the browser blocks all cross-origin requests.
# We allow both Vite's default port (5173) and Create React App's (3000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Create React App
        "http://localhost:5173",  # Vite (our frontend)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all /api/v1 routes.
# Every router registered inside v1_router is now reachable under /api/v1.
# Example: health.py's GET /health becomes GET /api/v1/health
app.include_router(v1_router, prefix="/api/v1")
