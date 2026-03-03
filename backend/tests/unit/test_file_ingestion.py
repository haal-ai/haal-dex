"""Unit tests for FileIngestionService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fastapi import UploadFile
from io import BytesIO

from app.models.encryption import EncryptionConfig
from app.models.files import SUPPORTED_FORMATS
from app.services.file_ingestion import FileIngestionService


def _make_upload_file(filename: str, content: bytes = b"test content") -> UploadFile:
    """Create a minimal UploadFile for testing."""
    return UploadFile(filename=filename, file=BytesIO(content))


@pytest.fixture
def service() -> FileIngestionService:
    return FileIngestionService()


# ── validate_format ──────────────────────────────────────────────────

class TestValidateFormat:
    @pytest.mark.asyncio
    async def test_supported_formats_accepted(self, service: FileIngestionService) -> None:
        for fmt in SUPPORTED_FORMATS:
            file = _make_upload_file(f"test.{fmt}")
            result = await service.validate_format(file)
            assert result.valid is True
            assert result.detected_format == fmt
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_uppercase_extension_normalised(self, service: FileIngestionService) -> None:
        file = _make_upload_file("report.PDF")
        result = await service.validate_format(file)
        assert result.valid is True
        assert result.detected_format == "pdf"

    @pytest.mark.asyncio
    async def test_unsupported_format_rejected(self, service: FileIngestionService) -> None:
        file = _make_upload_file("image.png")
        result = await service.validate_format(file)
        assert result.valid is False
        assert result.detected_format == "png"
        assert "Unsupported file format" in (result.error_message or "")
        assert "png" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_no_extension_rejected(self, service: FileIngestionService) -> None:
        file = _make_upload_file("README")
        result = await service.validate_format(file)
        assert result.valid is False
        assert result.detected_format is None

    @pytest.mark.asyncio
    async def test_empty_filename_rejected(self, service: FileIngestionService) -> None:
        file = _make_upload_file("")
        result = await service.validate_format(file)
        assert result.valid is False


# ── upload ───────────────────────────────────────────────────────────

class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_valid_files(self, service: FileIngestionService) -> None:
        files = [
            _make_upload_file("doc.pdf", b"pdf content"),
            _make_upload_file("notes.txt", b"text content"),
        ]
        result = await service.upload(files, session_id="sess-1")
        assert len(result) == 2
        assert result[0].original_name == "doc.pdf"
        assert result[0].format == "pdf"
        assert result[0].content == b"pdf content"
        assert result[0].session_id == "sess-1"
        assert result[0].was_encrypted is False
        assert result[1].original_name == "notes.txt"

    @pytest.mark.asyncio
    async def test_upload_unsupported_format_raises(self, service: FileIngestionService) -> None:
        files = [_make_upload_file("image.png")]
        with pytest.raises(ValueError, match="Unsupported file format"):
            await service.upload(files, session_id="sess-2")

    @pytest.mark.asyncio
    async def test_upload_generates_unique_ids(self, service: FileIngestionService) -> None:
        files = [
            _make_upload_file("a.pdf", b"a"),
            _make_upload_file("b.pdf", b"b"),
        ]
        result = await service.upload(files, session_id="sess-3")
        assert result[0].id != result[1].id

    @pytest.mark.asyncio
    async def test_upload_empty_list(self, service: FileIngestionService) -> None:
        result = await service.upload([], session_id="sess-4")
        assert result == []


# ── decrypt_if_needed ────────────────────────────────────────────────

class TestDecryptIfNeeded:
    @pytest.mark.asyncio
    async def test_no_decryption_when_disabled(self, service: FileIngestionService) -> None:
        from app.models.files import IngestedFile

        original = IngestedFile(
            id="f1", original_name="doc.pdf", format="pdf",
            size_bytes=5, content=b"hello", was_encrypted=False, session_id="s1",
        )
        config = EncryptionConfig(enabled=False, algorithm="", key_reference="", target="input")
        result = await service.decrypt_if_needed(original, config)
        assert result is original

    @pytest.mark.asyncio
    async def test_decryption_delegates_to_encryption_service(self) -> None:
        from unittest.mock import MagicMock
        from app.models.files import IngestedFile

        mock_enc = MagicMock()
        mock_enc.decrypt.return_value = b"decrypted"

        service = FileIngestionService(encryption_service=mock_enc)
        original = IngestedFile(
            id="f2", original_name="secret.pdf", format="pdf",
            size_bytes=10, content=b"encrypted!", was_encrypted=False, session_id="s2",
        )
        config = EncryptionConfig(
            enabled=True, algorithm="Fernet",
            key_reference="some-key", target="input",
        )
        result = await service.decrypt_if_needed(original, config)

        mock_enc.decrypt.assert_called_once_with(b"encrypted!", config)
        assert result.content == b"decrypted"
        assert result.was_encrypted is True
        assert result.id == "f2"
        assert result.size_bytes == len(b"decrypted")
