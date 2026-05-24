import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_aws_service, get_resource_scanner
from app.db.session import get_db
from app.jobs.cost_sync import sync_cost_data
from app.jobs.resource_scan import scan_resources
from app.services.aws_cost_service import AwsCostService
from app.services.resource_scanner import ResourceScanner

router = APIRouter(prefix="/admin", tags=["admin"])


class SyncResult(BaseModel):
    rows_upserted: int
    new_alerts_created: int
    duration_seconds: float


class ScanResult(BaseModel):
    findings_scanned: int
    recommendations_upserted: int
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
        summary = await sync_cost_data(db, aws)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SyncResult(
        rows_upserted=summary.cost_rows_upserted,
        new_alerts_created=summary.new_alerts_created,
        duration_seconds=round(time.perf_counter() - start, 3),
    )


@router.post("/scan-resources", response_model=ScanResult)
async def manual_scan_resources(
    db: AsyncSession = Depends(get_db),
    scanner: ResourceScanner = Depends(get_resource_scanner),
):
    """
    Trigger a resource scan immediately.

    Calls the same scan_resources() function the daily scheduler uses — runs
    every waste check, prices the findings, and upserts recommendations.
    Re-running is safe: existing recommendations are updated (last_seen_at
    bumped), never duplicated. Handy for live demos and first-run population.
    """
    start = time.perf_counter()

    try:
        summary = await scan_resources(db, scanner)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ScanResult(
        findings_scanned=summary.findings_scanned,
        recommendations_upserted=summary.recommendations_upserted,
        duration_seconds=round(time.perf_counter() - start, 3),
    )
