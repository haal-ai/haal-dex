"""Output preview and export API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.encryption_service import EncryptionService
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry

router = APIRouter(prefix="/api/output", tags=["output"])

_registry = TemplateRegistry()
_encryption = EncryptionService()
_generator = OutputGenerator(registry=_registry, encryption_service=_encryption)

# In-memory store of rendered documents keyed by session_id.
_rendered_docs: dict[str, RenderedDocument] = {}


def get_output_generator() -> OutputGenerator:
    return _generator


def get_template_registry() -> TemplateRegistry:
    return _registry


@router.get("/{session_id}/preview")
async def preview_output(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    generator: OutputGenerator = Depends(get_output_generator),
) -> dict:
    """Return a preview of the rendered output document for a session."""
    doc = _rendered_docs.get(session_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No rendered document found for this session")

    return {
        "session_id": doc.session_id,
        "template_id": doc.template_id,
        "format": doc.format,
        "content": doc.content.decode("utf-8", errors="replace"),
        "metadata": {
            "author": doc.metadata.author,
            "date": doc.metadata.date.isoformat() if isinstance(doc.metadata.date, datetime) else str(doc.metadata.date),
            "version": doc.metadata.version,
            "classification": doc.metadata.classification,
        },
        "validation_result": doc.validation_result,
    }


@router.get("/{session_id}/export")
async def export_output(
    session_id: str,
    format: str = Query(..., alias="format", description="Export format: pdf, xml, docx, md, html"),
    user: UserContext = Depends(get_current_user),
    generator: OutputGenerator = Depends(get_output_generator),
) -> dict:
    """Export the rendered document in the requested format.

    Returns the exported bytes as a base64-encoded string for simplicity.
    A production implementation would return a streaming binary response.
    """
    import base64

    doc = _rendered_docs.get(session_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No rendered document found for this session")

    allowed = {"pdf", "xml", "docx", "md", "html"}
    if format not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format!r}. Must be one of {sorted(allowed)}")

    try:
        exported = await generator.export(doc, format)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    return {
        "session_id": session_id,
        "format": format,
        "data": base64.b64encode(exported).decode("ascii"),
        "size_bytes": len(exported),
    }
