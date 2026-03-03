from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.encryption import EncryptionConfig


@dataclass
class ValidationRule:
    field: str
    rule_type: str  # "required" | "format" | "cross_reference" | "regex"
    parameters: dict


# A list of validation error strings; empty means valid.
ValidationResult = list[str]


@dataclass
class DocumentMetadata:
    author: str
    date: datetime
    version: str
    classification: str


@dataclass
class Template:
    id: str
    name: str
    format: str  # "pdf" | "docx" | "md" | "html" | "pptx"
    structure: dict
    validation_rules: list[ValidationRule]
    required_metadata: list[str]  # e.g. ["author", "date", "version", "classification"]
    encryption_settings: EncryptionConfig | None
    jinja2_template_path: str


@dataclass
class RenderedDocument:
    id: str
    session_id: str
    template_id: str
    format: str
    content: bytes
    metadata: DocumentMetadata
    validation_result: ValidationResult
