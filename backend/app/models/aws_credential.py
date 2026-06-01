from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AwsCredential(Base):
    """
    One row = one user's stored AWS credentials.

    The access key id and secret access key are NEVER stored in the clear: both
    are Fernet-encrypted (see app/services/crypto_service.py) before they reach
    this table, and decrypted only at the moment a cost sync or resource scan
    needs to call AWS.

    `access_key_last4` is the only plaintext fingerprint we keep, purely so the
    Settings page can show a masked "····NAV" hint of which key is saved without
    ever decrypting or exposing the real value.

    Security note (FYP-honest): users MUST supply READ-ONLY IAM credentials.
    Production would avoid storing long-lived secrets at all (IAM role
    assumption via sts:AssumeRole) and keep the encryption key in a managed KMS.
    """

    __tablename__ = "aws_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)

    # One credential set per user. unique=True enforces it at the DB level, and
    # the ON DELETE CASCADE means deleting a user cleans up their secrets too.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Fernet ciphertext (base64 text, longer than the plaintext). Text, not a
    # bounded String, so we never risk truncating a token.
    access_key_id_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_access_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Last 4 chars of the access key id, in the clear, for the masked display.
    access_key_last4: Mapped[str] = mapped_column(String(4), nullable=False)

    region: Mapped[str] = mapped_column(String(32), nullable=False, default="us-east-1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
