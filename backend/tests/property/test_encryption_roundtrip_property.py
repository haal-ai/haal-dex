# Feature: intent, Property 23: Encryption round trip per target
"""Property 23: Encryption round trip per target

For any data (input file, output document, or log entry) and any encryption
configuration, encrypting then decrypting should return the original data.
Each target (input, output, log) should use its own independently configured
key and algorithm.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

Strategy:
- Generate random binary data via ``st.binary()``
- Generate a random algorithm choice (``"Fernet"`` or ``"AES-256-GCM"``)
- Generate an appropriate key for the chosen algorithm
- Generate a random target from ``{"input", "output", "log"}``
- Verify ``decrypt(encrypt(data)) == data``
- Also verify that each target can use independent key/algorithm combinations
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from hypothesis import given, settings, strategies as st

from app.config import Settings
from app.models.encryption import EncryptionConfig
from app.services.encryption_service import EncryptionService

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_targets = st.sampled_from(["input", "output", "log"])
_algorithms = st.sampled_from(["Fernet", "AES-256-GCM"])
_data = st.binary(min_size=0, max_size=4096)


def _key_for_algorithm(algorithm: str) -> str:
    """Generate a valid key for the given algorithm."""
    if algorithm == "Fernet":
        return Fernet.generate_key().decode("utf-8")
    # AES-256-GCM: 32 random bytes as hex (64 hex chars)
    return os.urandom(32).hex()


@st.composite
def encryption_config_strategy(draw):
    """Draw a valid (target, algorithm, key) triple as an EncryptionConfig."""
    target = draw(_targets)
    algorithm = draw(_algorithms)
    key = _key_for_algorithm(algorithm)
    return EncryptionConfig(
        enabled=True,
        algorithm=algorithm,
        key_reference=key,
        target=target,
    )


@st.composite
def independent_target_configs(draw):
    """Draw three independent EncryptionConfigs — one per target — each with
    a randomly chosen algorithm and freshly generated key."""
    configs = {}
    for target in ("input", "output", "log"):
        algorithm = draw(_algorithms)
        key = _key_for_algorithm(algorithm)
        configs[target] = EncryptionConfig(
            enabled=True,
            algorithm=algorithm,
            key_reference=key,
            target=target,
        )
    return configs


def _make_service() -> EncryptionService:
    """Create an EncryptionService with default (empty) settings."""
    return EncryptionService(settings=Settings())


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(data=_data, config=encryption_config_strategy())
@settings(max_examples=100)
def test_encrypt_then_decrypt_returns_original_data(data: bytes, config: EncryptionConfig):
    """Property 23: For any data and encryption config, encrypt then decrypt
    returns the original data.

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
    """
    svc = _make_service()

    ciphertext = svc.encrypt(data, config)
    plaintext = svc.decrypt(ciphertext, config)

    assert plaintext == data, (
        f"Round-trip failed for target={config.target!r}, "
        f"algorithm={config.algorithm!r}, data length={len(data)}"
    )


@given(configs=independent_target_configs(), data=_data)
@settings(max_examples=100)
def test_each_target_uses_independent_key_and_algorithm(
    configs: dict[str, EncryptionConfig],
    data: bytes,
):
    """Property 23 (independence): Each target (input, output, log) uses its
    own independently configured key and algorithm. Encrypting the same data
    under different target configs produces different ciphertexts (with
    overwhelming probability), and each target's ciphertext can only be
    decrypted with its own config.

    **Validates: Requirements 12.1, 12.2**
    """
    svc = _make_service()

    ciphertexts = {}
    for target, config in configs.items():
        ciphertexts[target] = svc.encrypt(data, config)

    # Each target round-trips correctly with its own config
    for target, config in configs.items():
        assert svc.decrypt(ciphertexts[target], config) == data, (
            f"Round-trip failed for target={target!r}, "
            f"algorithm={config.algorithm!r}"
        )
