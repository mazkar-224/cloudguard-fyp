from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """
    One row = one person who can log into CloudGuard.

    We never store the plaintext password — only a bcrypt hash in
    `hashed_password`. The email is the login identifier and is unique so the
    same address can't register twice (the DB enforces it, not just the app).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Login identifier. unique=True adds a DB-level constraint so a duplicate
    # registration fails even under a race between two simultaneous requests.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)

    # bcrypt hash (a ~60-char string). NEVER the raw password. String(255)
    # leaves comfortable headroom over bcrypt's fixed-length output.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
