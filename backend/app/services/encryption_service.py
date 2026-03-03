"""Encryption service with configurable per-target encryption.

Supports Fernet and AES-256-GCM algorithms with independent configuration
for input, output, and log targets.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings, get_settings
from app.models.encryption import EncryptionConfig

# AES-256-GCM nonce size in bytes (96 bits is the recommended size).
_AES_GCM_NONCE_BYTES = 12


class EncryptionService:
    """Handles encryption and decryption for input, output, and log targets.

    Each target (``"input"``, ``"output"``, ``"log"``) can be independently
    configured with its own key and algorithm (``"Fernet"`` or
    ``"AES-256-GCM"``).
    """

    _VALID_TARGETS = {"input", "output", "log"}
    _VALID_ALGORITHMS = {"Fernet", "AES-256-GCM"}

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, data: bytes, config: EncryptionConfig) -> bytes:
        """Encrypt *data* using the algorithm and key specified in *config*.

        For **Fernet** the returned bytes are the Fernet token.
        For **AES-256-GCM** a random 12-byte nonce is generated and prepended
        to the ciphertext (``nonce || ciphertext``).

        Raises ``ValueError`` for unsupported algorithms or missing keys.
        """
        self._validate_config(config)

        if not config.enabled:
            return data

        if config.algorithm == "Fernet":
            return self._fernet_encrypt(data, config.key_reference)
        elif config.algorithm == "AES-256-GCM":
            return self._aesgcm_encrypt(data, config.key_reference)
        # _validate_config already guards against unknown algorithms, but
        # keep a defensive fallback.
        raise ValueError(f"Unsupported algorithm: {config.algorithm}")  # pragma: no cover

    def decrypt(self, data: bytes, config: EncryptionConfig) -> bytes:
        """Decrypt *data* using the algorithm and key specified in *config*.

        For **AES-256-GCM** the first 12 bytes of *data* are treated as the
        nonce.

        Raises ``ValueError`` for unsupported algorithms or missing keys.
        """
        self._validate_config(config)

        if not config.enabled:
            return data

        if config.algorithm == "Fernet":
            return self._fernet_decrypt(data, config.key_reference)
        elif config.algorithm == "AES-256-GCM":
            return self._aesgcm_decrypt(data, config.key_reference)
        raise ValueError(f"Unsupported algorithm: {config.algorithm}")  # pragma: no cover

    def get_config(self, target: str) -> EncryptionConfig:
        """Build an ``EncryptionConfig`` for *target* from application settings.

        *target* must be one of ``"input"``, ``"output"``, or ``"log"``.

        The key is read from the corresponding ``encryption_key_<target>``
        setting.  If the key is empty the config is returned with
        ``enabled=False``.

        The algorithm is inferred from the key format:
        - URL-safe base64 keys of 44 characters → ``"Fernet"``
        - Otherwise → ``"AES-256-GCM"`` (key is treated as hex-encoded)
        """
        if target not in self._VALID_TARGETS:
            raise ValueError(
                f"Invalid encryption target: {target!r}. "
                f"Must be one of {sorted(self._VALID_TARGETS)}."
            )

        key = self._key_for_target(target)

        if not key:
            return EncryptionConfig(
                enabled=False,
                algorithm="",
                key_reference="",
                target=target,
            )

        algorithm = self._detect_algorithm(key)

        return EncryptionConfig(
            enabled=True,
            algorithm=algorithm,
            key_reference=key,
            target=target,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key_for_target(self, target: str) -> str:
        """Return the raw key string for *target* from settings."""
        mapping = {
            "input": self._settings.encryption_key_input,
            "output": self._settings.encryption_key_output,
            "log": self._settings.encryption_key_log,
        }
        return mapping[target]

    @staticmethod
    def _detect_algorithm(key: str) -> str:
        """Heuristic: Fernet keys are 44-char URL-safe base64 strings."""
        if len(key) == 44 and key.endswith("="):
            return "Fernet"
        return "AES-256-GCM"

    # -- Fernet --------------------------------------------------------

    @staticmethod
    def _fernet_encrypt(data: bytes, key: str) -> bytes:
        f = Fernet(key.encode("utf-8"))
        return f.encrypt(data)

    @staticmethod
    def _fernet_decrypt(data: bytes, key: str) -> bytes:
        f = Fernet(key.encode("utf-8"))
        return f.decrypt(data)

    # -- AES-256-GCM ---------------------------------------------------

    @staticmethod
    def _aesgcm_encrypt(data: bytes, hex_key: str) -> bytes:
        raw_key = bytes.fromhex(hex_key)
        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(_AES_GCM_NONCE_BYTES)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    @staticmethod
    def _aesgcm_decrypt(data: bytes, hex_key: str) -> bytes:
        raw_key = bytes.fromhex(hex_key)
        aesgcm = AESGCM(raw_key)
        nonce = data[:_AES_GCM_NONCE_BYTES]
        ciphertext = data[_AES_GCM_NONCE_BYTES:]
        return aesgcm.decrypt(nonce, ciphertext, None)

    # -- Validation ----------------------------------------------------

    def _validate_config(self, config: EncryptionConfig) -> None:
        """Raise ``ValueError`` if *config* is structurally invalid."""
        if config.target not in self._VALID_TARGETS:
            raise ValueError(
                f"Invalid encryption target: {config.target!r}. "
                f"Must be one of {sorted(self._VALID_TARGETS)}."
            )
        if config.enabled and config.algorithm not in self._VALID_ALGORITHMS:
            raise ValueError(
                f"Unsupported encryption algorithm: {config.algorithm!r}. "
                f"Must be one of {sorted(self._VALID_ALGORITHMS)}."
            )
        if config.enabled and not config.key_reference:
            raise ValueError("Encryption is enabled but no key_reference was provided.")
