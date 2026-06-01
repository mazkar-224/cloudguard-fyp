from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.aws_credential import AwsCredential
from app.models.user import User
from app.schemas.aws_credential import (
    AwsCredentialIn,
    AwsCredentialOut,
    TestConnectionResult,
)
from app.services import crypto_service
from app.services.credential_service import get_user_credential
from app.services.resource_scanner import ResourceScanner

router = APIRouter(prefix="/settings", tags=["settings"])


async def _healthcheck(payload: AwsCredentialIn) -> dict:
    """Validate the submitted credentials against AWS without saving them.

    Builds a throwaway ResourceScanner and calls its healthcheck — one cheap
    read (describe_regions) that confirms the keys are valid AND have the
    read permissions CloudGuard needs. Returns {"ok": bool, "detail": str}.
    A malformed key (e.g. blank) raises ValueError in the constructor, which
    we translate into the same {ok: False} shape.
    """
    try:
        scanner = ResourceScanner(
            aws_access_key_id=payload.access_key_id,
            aws_secret_access_key=payload.secret_access_key,
            region=payload.region,
        )
    except ValueError as exc:
        return {"ok": False, "detail": str(exc)}
    return await scanner.healthcheck()


@router.post("/test-connection", response_model=TestConnectionResult)
async def test_connection(payload: AwsCredentialIn):
    """
    Check whether the given credentials work, WITHOUT saving them.

    Backs the Settings page "Test connection" button so a user can confirm
    their keys before committing them. Always returns 200 with {ok, detail};
    a failure is reported in the body, not as an HTTP error.
    """
    result = await _healthcheck(payload)
    return TestConnectionResult(ok=result["ok"], detail=result["detail"])


@router.post(
    "/aws-credentials",
    response_model=AwsCredentialOut,
    status_code=status.HTTP_201_CREATED,
)
async def save_aws_credentials(
    payload: AwsCredentialIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save (or replace) the current user's AWS credentials.

    Flow:
      1. Validate against AWS via healthcheck — we never store credentials that
         don't work or lack read permissions (400 if they fail).
      2. Encrypt both the access key id and secret with Fernet before storing.
         The DB never holds either value in the clear.
      3. Upsert — one credential set per user, so re-submitting overwrites.

    The response is masked (last-4 + region only); the secret is never returned.
    """
    result = await _healthcheck(payload)
    if not result["ok"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AWS rejected these credentials: {result['detail']}",
        )

    access_key_id_encrypted = crypto_service.encrypt(payload.access_key_id)
    secret_access_key_encrypted = crypto_service.encrypt(payload.secret_access_key)
    last4 = payload.access_key_id[-4:]

    def _apply(target: AwsCredential) -> None:
        target.access_key_id_encrypted = access_key_id_encrypted
        target.secret_access_key_encrypted = secret_access_key_encrypted
        target.access_key_last4 = last4
        target.region = payload.region

    cred = await get_user_credential(db, current_user.id)
    if cred is None:
        cred = AwsCredential(user_id=current_user.id)
        db.add(cred)
    _apply(cred)

    try:
        await db.commit()
    except IntegrityError:
        # Concurrent first-time save: two inserts raced and this one lost the
        # unique(user_id) constraint. Roll back and update the row that won, so
        # the latest save still takes effect (last write wins) rather than 500.
        await db.rollback()
        cred = await get_user_credential(db, current_user.id)
        if cred is None:
            cred = AwsCredential(user_id=current_user.id)
            db.add(cred)
        _apply(cred)
        await db.commit()

    await db.refresh(cred)
    return cred


@router.get("/aws-credentials", response_model=AwsCredentialOut | None)
async def get_aws_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the current user's saved credential — masked.

    Returns null if none is saved. NEVER returns the secret access key or the
    full access key id: only the last 4 chars (for a "····5NAV" hint), region,
    and timestamps. The secret is write-only from the API's perspective.
    """
    cred = await get_user_credential(db, current_user.id)
    return cred


@router.delete("/aws-credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aws_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove the current user's saved credentials.

    Idempotent — deleting when nothing is saved still returns 204. After this,
    on-demand sync/scan will 400 until the user saves credentials again.
    """
    cred = await get_user_credential(db, current_user.id)
    if cred is not None:
        await db.delete(cred)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
