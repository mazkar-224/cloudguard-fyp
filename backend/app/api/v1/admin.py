import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.jobs.cost_sync import sync_cost_data
from app.jobs.resource_scan import scan_resources
from app.models.user import User
from app.services.credential_service import (
    NoCredentialsError,
    build_cost_service_for_user,
    build_scanner_for_user,
)
from app.services.crypto_service import EncryptionError

# Message shown when a user's stored credentials can't be decrypted — almost
# always because ENCRYPTION_KEY was changed since they were saved. Re-saving on
# the Settings page re-encrypts them under the current key.
_DECRYPT_ERROR_DETAIL = (
    "Your saved AWS credentials could not be decrypted (the encryption key may "
    "have changed). Please re-enter them on the Settings page."
)

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a cost data sync immediately, using the LOGGED-IN USER's own AWS
    credentials (saved on the Settings page, decrypted just-in-time).

    Calls the same sync_cost_data() function the scheduler uses — so this is
    a real sync, not a mock. Useful for:
      - Populating the database on first run (scheduler hasn't fired yet)
      - Live demos: hit this, then refresh the dashboard charts
      - Testing that your AWS credentials and permissions work

    Returns 400 if the user hasn't saved credentials yet.
    """
    start = time.perf_counter()

    try:
        aws = await build_cost_service_for_user(db, current_user.id)
    except NoCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EncryptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_DECRYPT_ERROR_DETAIL) from exc

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a resource scan immediately, using the LOGGED-IN USER's own AWS
    credentials (saved on the Settings page, decrypted just-in-time).

    Calls the same scan_resources() function the daily scheduler uses — runs
    every waste check, prices the findings, and upserts recommendations.
    Re-running is safe: existing recommendations are updated (last_seen_at
    bumped), never duplicated. Handy for live demos and first-run population.

    Returns 400 if the user hasn't saved credentials yet.
    """
    start = time.perf_counter()

    try:
        scanner = await build_scanner_for_user(db, current_user.id)
    except NoCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EncryptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_DECRYPT_ERROR_DETAIL) from exc

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
