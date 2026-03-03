from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EncryptionConfig:
    enabled: bool
    algorithm: str  # e.g. "AES-256-GCM", "Fernet"
    key_reference: str  # reference to key in key store
    target: str  # "input" | "output" | "log"
