"""Unit tests for EncryptionService."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.models.encryption import EncryptionConfig
from app.services.encryption_service import EncryptionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fernet_key() -> str:
    """Generate a fresh Fernet key (URL-safe base64, 44 chars)."""
    return Fernet.generate_key().decode("utf-8")


def _aes256_hex_key() -> str:
    """Generate a random 256-bit key as a hex string (64 hex chars)."""
    return os.urandom(32).hex()


def _make_service(
    key_input: str = "",
    key_output: str = "",
    key_log: str = "",
) -> EncryptionService:
    settings = Settings(
        encryption_key_input=key_input,
        encryption_key_output=key_output,
        encryption_key_log=key_log,
    )
    return EncryptionService(settings=settings)


# ---------------------------------------------------------------------------
# Fernet round-trip
# ---------------------------------------------------------------------------

class TestFernetEncryption:
    def test_encrypt_decrypt_round_trip(self):
        key = _fernet_key()
        svc = _make_service(key_input=key)
        config = EncryptionConfig(enabled=True, algorithm="Fernet", key_reference=key, target="input")

        plaintext = b"hello world"
        ciphertext = svc.encrypt(plaintext, config)
        assert ciphertext != plaintext
        assert svc.decrypt(ciphertext, config) == plaintext

    def test_encrypt_empty_data(self):
        key = _fernet_key()
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="Fernet", key_reference=key, target="output")

        ciphertext = svc.encrypt(b"", config)
        assert svc.decrypt(ciphertext, config) == b""


# ---------------------------------------------------------------------------
# AES-256-GCM round-trip
# ---------------------------------------------------------------------------

class TestAES256GCMEncryption:
    def test_encrypt_decrypt_round_trip(self):
        key = _aes256_hex_key()
        svc = _make_service(key_output=key)
        config = EncryptionConfig(enabled=True, algorithm="AES-256-GCM", key_reference=key, target="output")

        plaintext = b"sensitive data"
        ciphertext = svc.encrypt(plaintext, config)
        assert ciphertext != plaintext
        assert svc.decrypt(ciphertext, config) == plaintext

    def test_nonce_prepended(self):
        key = _aes256_hex_key()
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="AES-256-GCM", key_reference=key, target="log")

        ciphertext = svc.encrypt(b"data", config)
        # Ciphertext must be longer than 12 bytes (nonce) + 16 bytes (GCM tag) + plaintext
        assert len(ciphertext) > 12 + 16

    def test_encrypt_empty_data(self):
        key = _aes256_hex_key()
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="AES-256-GCM", key_reference=key, target="input")

        ciphertext = svc.encrypt(b"", config)
        assert svc.decrypt(ciphertext, config) == b""


# ---------------------------------------------------------------------------
# Disabled encryption passthrough
# ---------------------------------------------------------------------------

class TestDisabledEncryption:
    def test_encrypt_returns_original_when_disabled(self):
        svc = _make_service()
        config = EncryptionConfig(enabled=False, algorithm="", key_reference="", target="input")

        data = b"unchanged"
        assert svc.encrypt(data, config) is data

    def test_decrypt_returns_original_when_disabled(self):
        svc = _make_service()
        config = EncryptionConfig(enabled=False, algorithm="", key_reference="", target="output")

        data = b"unchanged"
        assert svc.decrypt(data, config) is data


# ---------------------------------------------------------------------------
# get_config()
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_returns_disabled_when_no_key(self):
        svc = _make_service()
        cfg = svc.get_config("input")
        assert cfg.enabled is False
        assert cfg.target == "input"

    def test_detects_fernet_algorithm(self):
        key = _fernet_key()
        svc = _make_service(key_input=key)
        cfg = svc.get_config("input")
        assert cfg.enabled is True
        assert cfg.algorithm == "Fernet"
        assert cfg.key_reference == key
        assert cfg.target == "input"

    def test_detects_aes_algorithm(self):
        key = _aes256_hex_key()
        svc = _make_service(key_output=key)
        cfg = svc.get_config("output")
        assert cfg.enabled is True
        assert cfg.algorithm == "AES-256-GCM"
        assert cfg.key_reference == key
        assert cfg.target == "output"

    def test_each_target_independent(self):
        fernet_key = _fernet_key()
        aes_key = _aes256_hex_key()
        svc = _make_service(key_input=fernet_key, key_output=aes_key, key_log="")

        input_cfg = svc.get_config("input")
        output_cfg = svc.get_config("output")
        log_cfg = svc.get_config("log")

        assert input_cfg.algorithm == "Fernet"
        assert output_cfg.algorithm == "AES-256-GCM"
        assert log_cfg.enabled is False

    def test_invalid_target_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Invalid encryption target"):
            svc.get_config("unknown")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_unsupported_algorithm_raises(self):
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="ROT13", key_reference="key", target="input")
        with pytest.raises(ValueError, match="Unsupported encryption algorithm"):
            svc.encrypt(b"data", config)

    def test_missing_key_raises(self):
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="Fernet", key_reference="", target="input")
        with pytest.raises(ValueError, match="no key_reference"):
            svc.encrypt(b"data", config)

    def test_invalid_target_in_config_raises(self):
        svc = _make_service()
        config = EncryptionConfig(enabled=True, algorithm="Fernet", key_reference="k", target="bad")
        with pytest.raises(ValueError, match="Invalid encryption target"):
            svc.encrypt(b"data", config)
