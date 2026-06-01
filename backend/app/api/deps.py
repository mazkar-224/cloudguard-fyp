from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import decode_access_token
from app.services.aws_cost_service import AwsCostService
from app.services.resource_scanner import ResourceScanner


@lru_cache(maxsize=1)
def get_aws_service() -> AwsCostService:
    """
    FastAPI dependency — returns a singleton AwsCostService.

    lru_cache(maxsize=1) means the service is created exactly once the first
    time a route needs it, then the same instance is reused for every request.
    This is efficient because it avoids creating a new boto3 client per request.

    Usage in a route:
        from fastapi import Depends
        from app.api.deps import get_aws_service

        @router.get("/costs/daily")
        async def daily_costs(service: AwsCostService = Depends(get_aws_service)):
            return await service.get_daily_costs()
    """
    return AwsCostService(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


@lru_cache(maxsize=1)
def get_resource_scanner() -> ResourceScanner:
    """
    FastAPI dependency — returns a singleton ResourceScanner.

    Same singleton pattern as get_aws_service: the boto3 EC2/CloudWatch clients
    are built once and reused. Unlike Cost Explorer, EC2/CloudWatch are regional,
    so we pass settings.aws_region.
    """
    return ResourceScanner(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region=settings.aws_region,
    )


# ── Authentication ─────────────────────────────────────────────────────────

# HTTPBearer reads the `Authorization: Bearer <token>` header. auto_error=False
# means a missing header gives us `None` rather than FastAPI's generic 403, so
# we can raise our own clear 401 with a WWW-Authenticate hint.
_bearer_scheme = HTTPBearer(auto_error=False)

# Reused for every auth failure — vague on purpose. We never reveal whether the
# token was missing, malformed, expired, or pointed at a deleted user, so an
# attacker learns nothing from the difference.
_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that turns a Bearer token into the logged-in User.

    Used two ways:
      - `current_user: User = Depends(get_current_user)` in a route that wants
        the user object (e.g. GET /auth/me).
      - `dependencies=[Depends(get_current_user)]` on a router to simply gate
        access without the route caring who the user is.

    Raises 401 if the token is missing, invalid/expired, or names a user that
    no longer exists.
    """
    if credentials is None:
        raise _credentials_error

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _credentials_error

    user = await db.get(User, user_id)
    if user is None:
        raise _credentials_error

    return user
