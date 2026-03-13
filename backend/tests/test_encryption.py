"""Tests for Fernet encryption service."""

import pytest

from app.services.encryption import (
    decrypt_secret,
    encrypt_secret,
    reset_fernet,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_fernet()
    yield
    reset_fernet()


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        plaintext = "sk-secret-api-key-12345"
        ciphertext = encrypt_secret(plaintext)
        assert ciphertext != plaintext
        assert decrypt_secret(ciphertext) == plaintext

    def test_different_plaintexts_produce_different_ciphertexts(self) -> None:
        c1 = encrypt_secret("secret-a")
        c2 = encrypt_secret("secret-b")
        assert c1 != c2

    def test_same_plaintext_produces_different_ciphertexts(self) -> None:
        """Fernet uses timestamps + random IV, so same input → different output."""
        c1 = encrypt_secret("same-secret")
        c2 = encrypt_secret("same-secret")
        assert c1 != c2
        # Both still decrypt to the same value
        assert decrypt_secret(c1) == decrypt_secret(c2) == "same-secret"

    def test_decrypt_invalid_token_raises(self) -> None:
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            decrypt_secret("not-a-valid-fernet-token")

    def test_encrypt_empty_string(self) -> None:
        ciphertext = encrypt_secret("")
        assert decrypt_secret(ciphertext) == ""
