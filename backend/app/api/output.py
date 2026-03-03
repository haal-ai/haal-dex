"""Output preview and export API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.encryption_service import EncryptionService
from app.services.output_generator import OutputGenerator
from app.services.template_defaults import get_default_template_registry
from app.services.template_registry import TemplateRegistry

router = APIRouter(prefix="/api/output", tags=["output"])

_registry = get_default_template_registry()
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

    try:
        tpl = _registry.get_template(doc.template_id)
        template_name = tpl.name
    except Exception:
        template_name = doc.template_id

    text = doc.content.decode("utf-8", errors="replace")
    if doc.format == "html":
        content_html = text
    elif doc.format == "md":
        try:
            import markdown as md  # type: ignore[import-untyped]
            content_html = md.markdown(text, extensions=["extra"], output_format="html5")
        except Exception:
            content_html = f"<pre>{escape(text)}</pre>"
    else:
        content_html = f"<pre>{escape(text)}</pre>"

    return {
        "session_id": doc.session_id,
        "template_id": doc.template_id,
        "template_name": template_name,
        "format": doc.format,
        "content_html": content_html,
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
    format: str = Query(..., alias="format", description="Export format: pdf, docx, md, html, pptx"),
    user: UserContext = Depends(get_current_user),
    generator: OutputGenerator = Depends(get_output_generator),
) -> dict:
    """Export the rendered document in the requested format."""

    doc = _rendered_docs.get(session_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No rendered document found for this session")

    allowed = {"pdf", "docx", "md", "html", "pptx"}
    if format not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format!r}. Must be one of {sorted(allowed)}")

    try:
        exported = await generator.export(doc, format)
    except RuntimeError as exc:
        if format == "pdf":
            raise HTTPException(status_code=424, detail=str(exc))
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "md": "text/markdown; charset=utf-8",
        "html": "text/html; charset=utf-8",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }

    return Response(
        content=exported,
        media_type=media_types.get(format, "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename=output.{format}"},
    )
