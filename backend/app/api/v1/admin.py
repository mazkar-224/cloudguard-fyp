import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_aws_service
from app.db.session import get_db
from app.jobs.cost_sync import sync_cost_data
from app.services.aws_cost_service import AwsCostService

router = APIRouter(prefix="/admin", tags=["admin"])


class SyncResult(BaseModel):
    rows_upserted: int
    duration_seconds: float


@router.post("/sync", response_model=SyncResult)
async def manual_sync(
    db: AsyncSession = Depends(get_db),
    aws: AwsCostService = Depends(get_aws_service),
):
    """
    Trigger a cost data sync immediately.

    Calls the same sync_cost_data() function the scheduler uses — so this is
    a real sync, not a mock. Useful for:
      - Populating the database on first run (scheduler hasn't fired yet)
      - Live demos: hit this, then refresh the dashboard charts
      - Testing that your AWS credentials and permissions work
    """
    start = time.perf_counter()

    try:
        rows = await sync_cost_data(db, aws)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SyncResult(
        rows_upserted=rows,
        duration_seconds=round(time.perf_counter() - start, 3),
    )
