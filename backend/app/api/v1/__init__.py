from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import admin, alerts, auth, costs, health, recommendations, settings

# v1_router is the main router for version 1 of the API.
# Every endpoint file in this folder gets included here.
# main.py then mounts v1_router at the /api/v1 prefix.
#
# Why version the API?
#   If we ever break backwards compatibility (change a response shape,
#   remove a field), we can release /api/v2 without breaking existing
#   frontend code that still uses /api/v1.
v1_router = APIRouter()

# A single dependency that gates a whole router — every route inside the
# included router will 401 without a valid Bearer token. Declaring it here
# (rather than editing each route function) keeps the protection in one place
# and impossible to forget when new endpoints are added to these routers.
_auth_required = [Depends(get_current_user)]

# Public: liveness probes and the auth endpoints themselves must work without
# a token (you can't get a token if /auth/login is gated).
v1_router.include_router(health.router)
v1_router.include_router(auth.router)

# Protected: everything that exposes the user's cloud data or triggers AWS work.
v1_router.include_router(costs.router, dependencies=_auth_required)
v1_router.include_router(admin.router, dependencies=_auth_required)
v1_router.include_router(alerts.router, dependencies=_auth_required)
v1_router.include_router(recommendations.router, dependencies=_auth_required)
v1_router.include_router(settings.router, dependencies=_auth_required)
