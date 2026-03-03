"""File ingestion service — upload, validate, and optionally decrypt files."""

from __future__ import annotations

import uuid

from fastapi import UploadFile

from app.models.encryption import EncryptionConfig
from app.models.files import SUPPORTED_FORMATS, FileValidationResult, IngestedFile
from app.services.encryption_service import EncryptionService


class FileIngestionService:
    """Receives uploaded files, validates formats, and decrypts if needed."""

    def __init__(self, encryption_service: EncryptionService | None = None) -> None:
        self._encryption_service = encryption_service or EncryptionService()

    async def upload(
        self, files: list[UploadFile], session_id: str
    ) -> list[IngestedFile]:
        """Validate and ingest a list of uploaded files.

        Each file is validated against ``SUPPORTED_FORMATS``.  Files that
        pass validation are read into memory and returned as
        ``IngestedFile`` instances.

        Raises ``ValueError`` when *any* file has an unsupported format,
        including the specific format in the error message.
        """
        ingested: list[IngestedFile] = []

        for file in files:
            validation = await self.validate_format(file)
            if not validation.valid:
                raise ValueError(
                    validation.error_message
                    or f"Unsupported file format: {file.filename}"
                )

            content = await file.read()

            ingested.append(
                IngestedFile(
                    id=str(uuid.uuid4()),
                    original_name=file.filename or "unknown",
                    format=validation.detected_format or "",
                    size_bytes=len(content),
                    content=content,
                    was_encrypted=False,
                    session_id=session_id,
                )
            )

        return ingested

    async def validate_format(self, file: UploadFile) -> FileValidationResult:
        """Check whether *file*'s extension is in ``SUPPORTED_FORMATS``.

        Returns a ``FileValidationResult`` with ``valid=True`` when the
        normalised extension is supported, or ``valid=False`` with a
        descriptive error message otherwise.
        """
        filename = file.filename or ""
        ext = self._extract_extension(filename)

        if ext in SUPPORTED_FORMATS:
            return FileValidationResult(
                valid=True, detected_format=ext, error_message=None
            )

        return FileValidationResult(
            valid=False,
            detected_format=ext or None,
            error_message=(
                f"Unsupported file format: '{ext}'. "
                f"Supported formats are: {', '.join(sorted(SUPPORTED_FORMATS))}."
                if ext
                else f"Could not detect file format for '{filename}'. "
                f"Supported formats are: {', '.join(sorted(SUPPORTED_FORMATS))}."
            ),
        )

    async def decrypt_if_needed(
        self, file: IngestedFile, config: EncryptionConfig
    ) -> IngestedFile:
        """Decrypt *file* content when encryption is enabled in *config*.

        Delegates to ``EncryptionService.decrypt()``.  Returns a new
        ``IngestedFile`` with decrypted content and ``was_encrypted=True``
        when decryption was performed, or the original file unchanged.
        """
        if not config.enabled:
            return file

        decrypted_content = self._encryption_service.decrypt(
            file.content, config
        )

        return IngestedFile(
            id=file.id,
            original_name=file.original_name,
            format=file.format,
            size_bytes=len(decrypted_content),
            content=decrypted_content,
            was_encrypted=True,
            session_id=file.session_id,
        )

    @staticmethod
    def _extract_extension(filename: str) -> str:
        """Return the lowercase extension without the leading dot."""
        if "." not in filename:
            return ""
        return filename.rsplit(".", maxsplit=1)[-1].lower()
