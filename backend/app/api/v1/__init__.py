from fastapi import APIRouter

from app.api.v1 import health

# v1_router is the main router for version 1 of the API.
# Every endpoint file in this folder gets included here.
# main.py then mounts v1_router at the /api/v1 prefix.
#
# Why version the API?
#   If we ever break backwards compatibility (change a response shape,
#   remove a field), we can release /api/v2 without breaking existing
#   frontend code that still uses /api/v1.
v1_router = APIRouter()

v1_router.include_router(health.router)
