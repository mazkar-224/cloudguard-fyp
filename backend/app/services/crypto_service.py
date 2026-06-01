"""
Crypto service — encrypt/decrypt secrets at rest with Fernet.

We use this to protect each user's AWS secret access key in the database: the
plaintext secret is encrypted on the way in (POST /settings/aws-credentials) and
decrypted only at the moment a cost sync or resource scan actually needs to call
AWS. The DB never holds the secret in the clear.

Why Fernet?
  Fernet (from the `cryptography` library) is authenticated symmetric encryption
  (AES-128-CBC + HMAC). It's simple, hard to misuse, and includes integrity
  checking, so a tampered ciphertext fails loudly instead of decrypting to junk.

Honest limitation (state this in the viva):
  Fernet with a key in an environment variable is reasonable for an FYP, but a
  PRODUCTION system would:
    - keep the key in a managed key service (AWS KMS / Secrets Manager), not an
      env var, so the key is never on disk next to the data it protects; and
    - ideally avoid storing long-lived AWS secrets at all, using short-lived
      credentials via IAM role assumption (sts:AssumeRole) instead.
  Naming this limitation is a security-awareness win, not a weakness.

The Fernet instance is built lazily from settings.encryption_key (not at import
time) so the app still boots when the key is unset — only actually using
encryption raises. Reading settings at call time also lets tests inject a key.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionError(RuntimeError):
    """Raised when encryption/decryption can't proceed — missing/invalid key,
    or ciphertext that fails its integrity check."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """
    Build (once) the Fernet cipher from settings.encryption_key.

    lru_cache means we validate the key the first time encryption is used and
    reuse the cipher after. A missing or malformed key raises EncryptionError
    with guidance rather than a cryptic library error.
    """
    key = settings.encryption_key
    if not key:
        raise EncryptionError(
            "ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"\n'
            "then add it to your .env as ENCRYPTION_KEY=..."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise EncryptionError(
            "ENCRYPTION_KEY is not a valid Fernet key (must be 32 url-safe "
            "base64-encoded bytes). Regenerate it with Fernet.generate_key()."
        ) from exc


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the ciphertext as a str (safe to store)."""
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a stored ciphertext back to plaintext.

    Raises EncryptionError if the ciphertext is corrupt or was encrypted with a
    different key (e.g. the key was rotated) — never returns garbage silently.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError(
            "Could not decrypt — the data is corrupt or ENCRYPTION_KEY changed "
            "since it was stored."
        ) from exc
