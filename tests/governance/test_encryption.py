"""Tests for EncryptionManager (AES-256-GCM)."""

import base64
import os

import pytest

from src.exceptions import ConfigurationError
from src.governance.encryption import EncryptionConfig, EncryptionManager


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a default encryption key for all tests."""
    monkeypatch.setenv("ASAHI_ENCRYPTION_KEY", "test-passphrase-32-chars-long!!!")


@pytest.fixture
def manager() -> EncryptionManager:
    return EncryptionManager()


# ── Roundtrip ──────────────────────────────────────────


class TestEncryptDecrypt:
    def test_roundtrip_basic(self, manager: EncryptionManager) -> None:
        plaintext = "Hello, Asahi!"
        ct = manager.encrypt(plaintext)
        assert manager.decrypt(ct) == plaintext

    def test_roundtrip_empty_string(self, manager: EncryptionManager) -> None:
        ct = manager.encrypt("")
        assert manager.decrypt(ct) == ""

    def test_roundtrip_unicode(self, manager: EncryptionManager) -> None:
        text = "Unicode test: \u00e9\u00e8\u00ea \u2603 \U0001f600"
        ct = manager.encrypt(text)
        assert manager.decrypt(ct) == text

    def test_roundtrip_long_text(self, manager: EncryptionManager) -> None:
        text = "x" * 100_000
        ct = manager.encrypt(text)
        assert manager.decrypt(ct) == text

    def test_different_ciphertexts_each_call(
        self, manager: EncryptionManager
    ) -> None:
        """Each encryption uses a fresh salt+nonce, so outputs differ."""
        ct1 = manager.encrypt("same")
        ct2 = manager.encrypt("same")
        assert ct1 != ct2


# ── Wrong key / tamper ─────────────────────────────────


class TestDecryptionFailures:
    def test_wrong_key_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr1 = EncryptionManager()
        ct = mgr1.encrypt("secret")

        monkeypatch.setenv("ASAHI_ENCRYPTION_KEY", "different-key-entirely!!!!!")
        mgr2 = EncryptionManager()

        with pytest.raises(ValueError, match="Decryption failed"):
            mgr2.decrypt(ct)

    def test_tampered_ciphertext_fails(
        self, manager: EncryptionManager
    ) -> None:
        ct = manager.encrypt("secret")
        raw = bytearray(base64.b64decode(ct))
        raw[-1] ^= 0xFF  # flip last byte
        tampered = base64.b64encode(bytes(raw)).decode("ascii")

        with pytest.raises(ValueError, match="Decryption failed"):
            manager.decrypt(tampered)


# ── Key rotation ───────────────────────────────────────


class TestKeyRotation:
    def test_rotate_key(
        self, manager: EncryptionManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ct_old = manager.encrypt("before rotation")

        monkeypatch.setenv("ASAHI_NEW_KEY", "brand-new-passphrase-here!!!")
        manager.rotate_key("ASAHI_NEW_KEY")

        ct_new = manager.encrypt("after rotation")
        assert manager.decrypt(ct_new) == "after rotation"

        # old ciphertext encrypted with old key cannot be decrypted
        with pytest.raises(ValueError, match="Decryption failed"):
            manager.decrypt(ct_old)

    def test_rotate_key_missing_env(
        self, manager: EncryptionManager
    ) -> None:
        with pytest.raises(ConfigurationError):
            manager.rotate_key("NONEXISTENT_VAR")


# ── Hashing ────────────────────────────────────────────


class TestHashForAudit:
    def test_deterministic(self, manager: EncryptionManager) -> None:
        h1 = manager.hash_for_audit("hello")
        h2 = manager.hash_for_audit("hello")
        assert h1 == h2

    def test_hex_format(self, manager: EncryptionManager) -> None:
        h = manager.hash_for_audit("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_inputs_differ(
        self, manager: EncryptionManager
    ) -> None:
        assert manager.hash_for_audit("a") != manager.hash_for_audit("b")


# ── Config / Init ──────────────────────────────────────


class TestInit:
    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ASAHI_ENCRYPTION_KEY", raising=False)
        with pytest.raises(ConfigurationError):
            EncryptionManager()

    def test_custom_config(self) -> None:
        cfg = EncryptionConfig(pbkdf2_iterations=100_000, salt_length=32)
        mgr = EncryptionManager(config=cfg)
        ct = mgr.encrypt("custom config")
        assert mgr.decrypt(ct) == "custom config"
