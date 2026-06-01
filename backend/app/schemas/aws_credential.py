from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AwsCredentialIn(BaseModel):
    """Body for POST /settings/aws-credentials and POST /settings/test-connection.

    The user pastes an IAM access key id + secret access key here. We validate
    these against AWS (ResourceScanner.healthcheck) before ever storing them.

    SECURITY: users must supply READ-ONLY credentials (AWS-managed
    `ReadOnlyAccess` is enough). We say so loudly in the UI and docs — CloudGuard
    only ever reads cost/usage data, never mutates the account.
    """

    access_key_id: str = Field(min_length=16, max_length=128)
    secret_access_key: str = Field(min_length=16, max_length=128)
    region: str = Field(default="us-east-1", min_length=1, max_length=32)


class AwsCredentialOut(BaseModel):
    """A saved credential as returned by GET /settings/aws-credentials.

    Deliberately NEVER includes the secret access key, nor the full access key
    id — only the last 4 chars for a masked hint (e.g. "····5NAV") plus the
    region and timestamps. The secret never leaves the server after it's stored.
    """

    model_config = ConfigDict(from_attributes=True)

    access_key_last4: str
    region: str
    created_at: datetime
    updated_at: datetime


class TestConnectionResult(BaseModel):
    """Result of POST /settings/test-connection — mirrors ResourceScanner's
    healthcheck shape so the Settings page can show a green/red indicator."""

    ok: bool
    detail: str
