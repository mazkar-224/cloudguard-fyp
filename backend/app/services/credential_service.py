"""
Credential service — load a user's stored AWS credentials and turn them into
ready-to-use service clients.

This is the bridge between the encrypted-at-rest AwsCredential rows (written by
the Settings page) and the AWS service classes that actually do work. Cost sync
and resource scans call the helpers here to get a service built from the logged-
in user's OWN credentials, decrypted just-in-time, instead of the shared env
credentials.

The plaintext secret lives only in memory for the duration of a single request
— it's decrypted here, handed to a boto3 client, and never persisted again.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_credential import AwsCredential
from app.services import crypto_service
from app.services.aws_cost_service import AwsCostService
from app.services.resource_scanner import ResourceScanner


class NoCredentialsError(RuntimeError):
    """Raised when a user tries to run an AWS operation but hasn't saved any
    credentials yet. The API layer maps this to a 400 telling them to visit
    Settings."""


async def get_user_credential(db: AsyncSession, user_id: int) -> AwsCredential | None:
    """Return the user's stored credential row, or None if they haven't saved one."""
    result = await db.execute(
        select(AwsCredential).where(AwsCredential.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _decrypt(cred: AwsCredential) -> tuple[str, str, str]:
    """Decrypt a stored credential into (access_key_id, secret_access_key, region)."""
    access_key_id = crypto_service.decrypt(cred.access_key_id_encrypted)
    secret_access_key = crypto_service.decrypt(cred.secret_access_key_encrypted)
    return access_key_id, secret_access_key, cred.region


async def build_cost_service_for_user(db: AsyncSession, user_id: int) -> AwsCostService:
    """Build an AwsCostService from the user's decrypted credentials.

    Raises NoCredentialsError if the user hasn't saved any.
    """
    cred = await get_user_credential(db, user_id)
    if cred is None:
        raise NoCredentialsError(
            "No AWS credentials saved. Add them on the Settings page first."
        )
    access_key_id, secret_access_key, _region = _decrypt(cred)
    # Cost Explorer is global (us-east-1), so AwsCostService takes no region.
    return AwsCostService(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


async def build_scanner_for_user(db: AsyncSession, user_id: int) -> ResourceScanner:
    """Build a ResourceScanner from the user's decrypted credentials.

    Raises NoCredentialsError if the user hasn't saved any.
    """
    cred = await get_user_credential(db, user_id)
    if cred is None:
        raise NoCredentialsError(
            "No AWS credentials saved. Add them on the Settings page first."
        )
    access_key_id, secret_access_key, region = _decrypt(cred)
    return ResourceScanner(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region=region,
    )
