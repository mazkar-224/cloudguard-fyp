"""
Authentication service — password hashing and JWT handling.

This module is deliberately split into two concerns, both pure and easy to test:

  1. Passwords — hash on the way in, verify on login. We use the `bcrypt`
     library directly. bcrypt is slow *by design* (that's what makes
     brute-forcing stolen hashes expensive) and salts every hash automatically,
     so two users with the same password still get different stored hashes.

  2. Tokens — after a successful login we hand the client a signed JWT (via
     PyJWT). The client sends it back on every request; we verify the signature
     to trust it. The token carries the user id in `sub` and an expiry in `exp`.
     Nothing secret lives in the token, only the user id — it's signed, not
     encrypted.

Why bcrypt + PyJWT directly (not passlib / python-jose)?
  Both of those wrappers are effectively unmaintained: passlib 1.7.4 crashes
  on bcrypt >= 4.1 (it probes a `__about__` attribute that bcrypt removed), and
  python-jose still calls the deprecated `datetime.utcnow()`. Talking to the
  maintained libraries directly is simpler, warning-free, and not pinned to an
  old bcrypt.

The DB lookups (create/find users) live in the endpoints, not here, so this
file stays free of database wiring and trivially unit-testable.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# We sign with a dedicated secret if one is configured, otherwise fall back to
# the app's SECRET_KEY so the app still boots in local dev without extra setup.
_JWT_SECRET = settings.access_token_secret or settings.secret_key
_JWT_ALGORITHM = "HS256"

# bcrypt only hashes the first 72 bytes of input and *raises* on longer input.
# We truncate defensively so a very long passphrase logs a user in instead of
# 500-ing. 72 bytes is far more entropy than any password needs.
_BCRYPT_MAX_BYTES = 72


# ── Passwords ───────────────────────────────────────────────────────────────

def _to_bcrypt_bytes(password: str) -> bytes:
    """Encode to UTF-8 and trim to bcrypt's 72-byte ceiling on a char boundary."""
    encoded = password.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return encoded
    # Drop a trailing partial character if the cut landed mid-codepoint.
    return encoded[:_BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore").encode("utf-8")


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of `password` — safe to store in the DB.

    bcrypt.hashpw returns bytes; we decode to str for a clean text column.
    """
    hashed = bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """True if `plain_password` matches the stored bcrypt hash.

    Returns False (rather than raising) if the stored hash is malformed, so a
    corrupt row can never crash a login request.
    """
    try:
        return bcrypt.checkpw(
            _to_bcrypt_bytes(plain_password), hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


# ── Tokens ──────────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    """
    Mint a signed JWT for a logged-in user.

    `sub` (subject) holds the user id as a string — the JWT spec expects `sub`
    to be a string. `exp` is set from settings.access_token_expire_minutes;
    PyJWT rejects the token automatically once that time passes.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """
    Validate a JWT and return the user id it carries, or None if invalid.

    Returns None for anything untrustworthy — bad signature, expired, malformed,
    or a missing/non-integer `sub`. The caller turns None into a 401; we never
    raise here so token handling has exactly one failure path.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None
