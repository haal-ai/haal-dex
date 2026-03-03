# Feature: intent, Property 1: File format acceptance matches supported set
"""Property 1: File format acceptance matches supported set

For any file, accept iff format is in {PPTX, DOCX, PDF, TXT, HTML, MD};
reject others with error identifying the unsupported format.

**Validates: Requirements 1.2, 1.4**

Strategy:
- Generate random filenames with supported extensions → verify valid=True
  and detected_format matches
- Generate random filenames with unsupported extensions → verify valid=False
  and error_message mentions the unsupported format
- Generate filenames with no extension → verify valid=False
- Use st.sampled_from(SUPPORTED_FORMATS) for supported formats
- Use st.text() filtered to exclude supported formats for unsupported ones
"""

from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile
from hypothesis import given, settings, strategies as st

from app.models.files import SUPPORTED_FORMATS
from app.services.file_ingestion import FileIngestionService

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe characters for the filename stem (avoid dots to prevent extra extensions)
_filename_stem = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=30,
)

_supported_ext = st.sampled_from(sorted(SUPPORTED_FORMATS))

# Unsupported extensions: short alphabetic strings that are NOT in SUPPORTED_FORMATS
_unsupported_ext = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=1,
    max_size=10,
).filter(lambda ext: ext.lower() not in SUPPORTED_FORMATS)


def _make_upload(filename: str) -> UploadFile:
    """Create a minimal UploadFile with the given filename."""
    return UploadFile(filename=filename, file=BytesIO(b"dummy"))


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(stem=_filename_stem, ext=_supported_ext)
@settings(max_examples=100)
def test_supported_format_accepted(stem: str, ext: str):
    """Property 1 (accept): For any file whose extension is in
    {PPTX, DOCX, PDF, TXT, HTML, MD}, validate_format returns valid=True
    and detected_format matches the extension.

    **Validates: Requirements 1.2, 1.4**
    """
    svc = FileIngestionService()
    upload = _make_upload(f"{stem}.{ext}")
    result = _run(svc.validate_format(upload))

    assert result.valid is True, (
        f"Expected valid=True for supported extension '{ext}', "
        f"got valid=False with error: {result.error_message}"
    )
    assert result.detected_format == ext.lower(), (
        f"Expected detected_format='{ext.lower()}', got '{result.detected_format}'"
    )
    assert result.error_message is None


@given(stem=_filename_stem, ext=_unsupported_ext)
@settings(max_examples=100)
def test_unsupported_format_rejected_with_error(stem: str, ext: str):
    """Property 1 (reject): For any file whose extension is NOT in the
    supported set, validate_format returns valid=False and the error_message
    identifies the unsupported format.

    **Validates: Requirements 1.2, 1.4**
    """
    svc = FileIngestionService()
    upload = _make_upload(f"{stem}.{ext}")
    result = _run(svc.validate_format(upload))

    assert result.valid is False, (
        f"Expected valid=False for unsupported extension '{ext}', "
        f"got valid=True"
    )
    assert result.error_message is not None, (
        "Expected a non-None error_message for unsupported format"
    )
    assert ext.lower() in result.error_message.lower(), (
        f"Error message should mention the unsupported format '{ext}', "
        f"got: {result.error_message}"
    )


@given(stem=_filename_stem)
@settings(max_examples=100)
def test_no_extension_rejected(stem: str):
    """Property 1 (no extension): For any filename without an extension,
    validate_format returns valid=False.

    **Validates: Requirements 1.2, 1.4**
    """
    # Ensure the stem has no dots (which would create an extension)
    clean_stem = stem.replace(".", "")
    if not clean_stem:
        clean_stem = "file"

    svc = FileIngestionService()
    upload = _make_upload(clean_stem)
    result = _run(svc.validate_format(upload))

    assert result.valid is False, (
        f"Expected valid=False for filename without extension '{clean_stem}', "
        f"got valid=True"
    )
    assert result.error_message is not None, (
        "Expected a non-None error_message for file with no extension"
    )
