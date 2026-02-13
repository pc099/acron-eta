"""
Encryption manager for data-at-rest protection.

Provides AES-256-GCM encryption with PBKDF2 key derivation,
key rotation, and one-way hashing for audit logs.
"""

import base64
import hashlib
import logging
import os
import threading
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from pydantic import BaseModel, Field

from src.config import get_settings
from src.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

_SALT_LENGTH = 16
_NONCE_LENGTH = 12
_KEY_LENGTH = 32  # 256 bits


class EncryptionConfig(BaseModel):
    """Configuration for EncryptionManager.

    Attributes:
        key_env: Environment variable holding the encryption passphrase.
        pbkdf2_iterations: PBKDF2 iteration count for key derivation.
        salt_length: Length of random salt in bytes.
    """

    key_env: str = Field(default="ASAHI_ENCRYPTION_KEY")
    pbkdf2_iterations: int = Field(default=480_000, ge=100_000)
    salt_length: int = Field(default=_SALT_LENGTH, ge=8, le=64)


class EncryptionManager:
    """AES-256-GCM encryption with PBKDF2-derived keys.

    Args:
        config: Encryption configuration.

    Raises:
        ConfigurationError: If the encryption key env var is not set.
    """

    def __init__(self, config: Optional[EncryptionConfig] = None) -> None:
        if config is None:
            _s = get_settings().governance
            config = EncryptionConfig(
                key_env=_s.encryption_key_env,
                pbkdf2_iterations=_s.pbkdf2_iterations,
                salt_length=_s.salt_length,
            )
        self._config = config
        self._lock = threading.Lock()
        self._passphrase = self._load_passphrase(self._config.key_env)
        logger.info(
            "EncryptionManager initialised",
            extra={"key_env": self._config.key_env},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using AES-256-GCM.

        Args:
            plaintext: UTF-8 string to encrypt.

        Returns:
            Base64-encoded string containing ``salt || nonce || ciphertext+tag``.

        Raises:
            ConfigurationError: If encryption key is unavailable.
        """
        salt = os.urandom(self._config.salt_length)
        nonce = os.urandom(_NONCE_LENGTH)
        key = self._derive_key(self._passphrase, salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        blob = salt + nonce + ciphertext
        return base64.b64encode(blob).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a value produced by :meth:`encrypt`.

        Args:
            ciphertext: Base64-encoded encrypted blob.

        Returns:
            Original plaintext string.

        Raises:
            ValueError: If the ciphertext is tampered or the key is wrong.
        """
        blob = base64.b64decode(ciphertext)
        salt_len = self._config.salt_length
        salt = blob[:salt_len]
        nonce = blob[salt_len : salt_len + _NONCE_LENGTH]
        ct = blob[salt_len + _NONCE_LENGTH :]
        key = self._derive_key(self._passphrase, salt)
        aesgcm = AESGCM(key)
        try:
            plaintext_bytes = aesgcm.decrypt(nonce, ct, None)
        except Exception as exc:
            raise ValueError("Decryption failed: wrong key or tampered data") from exc
        return plaintext_bytes.decode("utf-8")

    def rotate_key(self, new_key_env: str) -> None:
        """Rotate to a new encryption passphrase.

        Args:
            new_key_env: Environment variable name for the new passphrase.

        Raises:
            ConfigurationError: If the new key env var is not set.
        """
        new_passphrase = self._load_passphrase(new_key_env)
        with self._lock:
            self._passphrase = new_passphrase
            self._config.key_env = new_key_env
        logger.info(
            "Encryption key rotated",
            extra={"new_key_env": new_key_env},
        )

    def hash_for_audit(self, text: str) -> str:
        """Produce a one-way SHA-256 hash for audit logging.

        Args:
            text: Text to hash.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_passphrase(self, env_var: str) -> bytes:
        """Load and validate the encryption passphrase from the environment.

        Args:
            env_var: Name of the environment variable.

        Returns:
            Passphrase as bytes.

        Raises:
            ConfigurationError: If the variable is unset or empty.
        """
        value = os.environ.get(env_var)
        if not value:
            raise ConfigurationError(
                f"Encryption key environment variable '{env_var}' is not set"
            )
        return value.encode("utf-8")

    def _derive_key(self, passphrase: bytes, salt: bytes) -> bytes:
        """Derive a 256-bit key from passphrase + salt via PBKDF2.

        Args:
            passphrase: Raw passphrase bytes.
            salt: Random salt bytes.

        Returns:
            Derived key (32 bytes).
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LENGTH,
            salt=salt,
            iterations=self._config.pbkdf2_iterations,
        )
        return kdf.derive(passphrase)
