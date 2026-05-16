from functools import lru_cache

from app.config import settings
from app.services.aws_cost_service import AwsCostService


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
