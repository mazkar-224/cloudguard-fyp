from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create the FastAPI application instance.
# `title` and `version` show up in the auto-generated API docs at /docs
app = FastAPI(
    title="CloudGuard API",
    version="0.1.0",
    description="AWS cost monitoring and anomaly detection",
)

# CORS (Cross-Origin Resource Sharing) lets the React frontend
# (running on localhost:5173) talk to this backend (localhost:8000).
# Without this, the browser blocks the requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server address
    allow_credentials=True,
    allow_methods=["*"],   # allow GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],   # allow any headers
)


# --- Routes will be registered here as we build them ---
# Example: app.include_router(auth_router, prefix="/api/auth")


@app.get("/health")
def health_check():
    """
    A simple endpoint to confirm the server is running.
    Call GET /health and you should get {"status": "ok"} back.
    Useful for Docker health checks and load balancer pings.
    """
    return {"status": "ok", "app": "CloudGuard"}
