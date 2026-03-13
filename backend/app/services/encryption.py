"""Fernet symmetric encryption for BYOM credential storage.

Auth header values for BYOM model endpoints are encrypted at rest.
Key source (in order):
  1. FERNET_KEY env var (base64-encoded 32-byte key)
  2. Derived from a stable fallback for development
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from app.config import get_settings

    settings = get_settings()

    if settings.fernet_key:
        key = settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key
    else:
        # Derive a stable dev-only key — NOT for production
        seed = b"asahio-dev-encryption-seed"
        derived = hashlib.sha256(seed).digest()
        key = base64.urlsafe_b64encode(derived)
        logger.warning("Using derived dev encryption key — set FERNET_KEY in production")

    _fernet = Fernet(key)
    return _fernet


def reset_fernet() -> None:
    """Clear the cached Fernet instance. Used in tests."""
    global _fernet
    _fernet = None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string and return base64-encoded ciphertext."""
    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext and return plaintext."""
    f = _get_fernet()
    plaintext = f.decrypt(ciphertext.encode("utf-8"))
    return plaintext.decode("utf-8")
