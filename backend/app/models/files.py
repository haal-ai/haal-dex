from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_FORMATS = {"pptx", "docx", "pdf", "txt", "html", "md"}


@dataclass
class IngestedFile:
    id: str
    original_name: str
    format: str  # "pptx" | "docx" | "pdf" | "txt" | "html" | "md"
    size_bytes: int
    content: bytes
    was_encrypted: bool
    session_id: str


@dataclass
class FileValidationResult:
    valid: bool
    detected_format: str | None
    error_message: str | None
