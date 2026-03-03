"""File upload endpoint — multipart, auth-protected.

Creates a session on upload and stores ingested files for later pipeline use.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.services.encryption_service import EncryptionService
from app.services.file_ingestion import FileIngestionService

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_file_ingestion_service() -> FileIngestionService:
    return FileIngestionService(encryption_service=EncryptionService())


@router.post("/upload")
async def upload_files(
    files: list[UploadFile],
    user: UserContext = Depends(get_current_user),
    service: FileIngestionService = Depends(_get_file_ingestion_service),
) -> dict:
    """Upload one or more files for processing.

    Accepts multipart file uploads.  Each file is validated against the
    supported format list.  Creates a session and stores ingested files
    for later pipeline use.  Returns metadata for each ingested file.

    Requires a valid Bearer token (auth-protected).
    """
    session_id = str(uuid.uuid4())

    try:
        ingested = await service.upload(files, session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {exc}",
        )

    # Attempt decryption if input encryption is configured
    encryption_service = EncryptionService()
    input_config = encryption_service.get_config("input")

    decrypted = []
    for file in ingested:
        try:
            decrypted.append(await service.decrypt_if_needed(file, input_config))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Decryption failed for file '{file.original_name}': {exc}",
            )

    # Store files for later pipeline use and create a session entry
    from app.api.pipeline import store_session_files, _sessions
    from app.models.session import Session
    from datetime import datetime, timezone

    session = Session(
        id=session_id,
        user_id=user.user_id,
        pipeline_config_id="",
        status="pending",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        input_files=[f.id for f in decrypted],
        output_documents=[],
    )
    _sessions[session_id] = session
    store_session_files(session_id, decrypted)

    return {
        "session_id": session_id,
        "files": [
            {
                "id": f.id,
                "original_name": f.original_name,
                "format": f.format,
                "size_bytes": f.size_bytes,
                "was_encrypted": f.was_encrypted,
            }
            for f in decrypted
        ],
    }
