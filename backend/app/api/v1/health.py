from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])

# APP_VERSION is the single source of truth for the version string.
# It appears in /health responses and in the Swagger docs title.
APP_VERSION = "0.2.0"


@router.get("/health")
def health_check():
    """
    Confirms the API is running and returns basic environment info.

    Useful for:
    - Docker health checks (container restarts if this fails)
    - AWS load balancer target group checks
    - A quick sanity check during development

    Returns:
        status:      "ok" if the server is running
        version:     the current app version
        environment: "development", "staging", or "production" from .env
    """
    return {
        "status": "ok",
        "version": APP_VERSION,
        "environment": settings.environment,
    }
