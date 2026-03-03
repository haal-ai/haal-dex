"""Output generator for rendering, validating, and exporting documents.

Uses Jinja2 for template rendering, and delegates to WeasyPrint (PDF),
python-docx (DOCX), and lxml (XML) for export.  Encryption is delegated
to :class:`EncryptionService` when the template has encryption settings.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.config import Settings, get_settings
from app.models.templates import (
    DocumentMetadata,
    RenderedDocument,
    Template,
    ValidationResult,
    ValidationRule,
)
from app.services.encryption_service import EncryptionService
from app.services.template_registry import TemplateRegistry


class OutputGenerator:
    """Renders, validates, and exports documents from templates."""

    def __init__(
        self,
        registry: TemplateRegistry,
        encryption_service: EncryptionService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry
        self._encryption = encryption_service or EncryptionService()
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    async def render(
        self,
        template_id: str,
        data: dict,
        metadata: DocumentMetadata,
        session_id: str = "",
    ) -> RenderedDocument:
        """Render a document by applying a Jinja2 template to *data*.

        The template is looked up in the :class:`TemplateRegistry` and its
        ``jinja2_template_path`` is loaded from the filesystem.  The
        *metadata* fields are injected into the template context alongside
        *data*.

        Returns a :class:`RenderedDocument` whose ``content`` is the
        rendered bytes (UTF-8 encoded).
        """
        template = self._registry.get_template(template_id)

        rendered_text = self._render_jinja2(template, data, metadata)

        content = rendered_text.encode("utf-8")

        # Encrypt if the template has encryption settings enabled.
        if template.encryption_settings and template.encryption_settings.enabled:
            content = self._encryption.encrypt(content, template.encryption_settings)

        validation_result = self._run_validation(rendered_text, template)

        return RenderedDocument(
            id=str(uuid.uuid4()),
            session_id=session_id,
            template_id=template_id,
            format=template.format,
            content=content,
            metadata=metadata,
            validation_result=validation_result,
        )

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    async def validate(
        self, document: RenderedDocument, template: Template
    ) -> ValidationResult:
        """Check *document* against *template* validation rules.

        Returns a list of human-readable violation strings.  An empty list
        means the document is valid.
        """
        text = document.content.decode("utf-8", errors="replace")
        return self._run_validation(text, template)

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    async def export(self, document: RenderedDocument, fmt: str) -> bytes:
        """Export *document* to the requested *fmt*.

        Supported formats: ``"pdf"``, ``"docx"``, ``"xml"``, ``"md"``,
        ``"html"``.
        """
        text = document.content.decode("utf-8", errors="replace")

        if fmt == "pdf":
            return self._export_pdf(text)
        elif fmt == "docx":
            return self._export_docx(text, document.metadata)
        elif fmt == "xml":
            return self._export_xml(text)
        elif fmt in ("md", "markdown"):
            return text.encode("utf-8")
        elif fmt == "html":
            return text.encode("utf-8")
        else:
            raise ValueError(f"Unsupported export format: {fmt!r}")

    # ------------------------------------------------------------------
    # Internal – Jinja2 rendering
    # ------------------------------------------------------------------

    def _render_jinja2(
        self, template: Template, data: dict, metadata: DocumentMetadata
    ) -> str:
        """Load the Jinja2 template file and render it."""
        tpl_path = Path(template.jinja2_template_path)

        env = Environment(
            loader=FileSystemLoader(str(tpl_path.parent)),
            autoescape=False,
        )

        try:
            jinja_tpl = env.get_template(tpl_path.name)
        except TemplateNotFound:
            raise FileNotFoundError(
                f"Jinja2 template not found: {template.jinja2_template_path}"
            )

        context = {
            **data,
            "metadata": {
                "author": metadata.author,
                "date": metadata.date.isoformat() if isinstance(metadata.date, datetime) else str(metadata.date),
                "version": metadata.version,
                "classification": metadata.classification,
            },
        }

        return jinja_tpl.render(context)

    # ------------------------------------------------------------------
    # Internal – validation
    # ------------------------------------------------------------------

    def _run_validation(self, text: str, template: Template) -> ValidationResult:
        """Run all validation rules against *text*."""
        violations: ValidationResult = []
        for rule in template.validation_rules:
            violation = self._check_rule(text, rule)
            if violation:
                violations.append(violation)
        return violations

    @staticmethod
    def _check_rule(text: str, rule: ValidationRule) -> str | None:
        """Return a violation message if *rule* is violated, else ``None``."""
        if rule.rule_type == "required":
            # The field value must appear in the text.
            if rule.field not in text:
                return f"Required field '{rule.field}' is missing from the document"

        elif rule.rule_type == "regex":
            pattern = rule.parameters.get("pattern", "")
            if pattern and not re.search(pattern, text):
                return (
                    f"Field '{rule.field}' does not match required pattern "
                    f"'{pattern}'"
                )

        elif rule.rule_type == "format":
            expected = rule.parameters.get("expected", "")
            if expected and expected not in text:
                return (
                    f"Field '{rule.field}' does not match expected format "
                    f"'{expected}'"
                )

        elif rule.rule_type == "cross_reference":
            ref_field = rule.parameters.get("reference_field", "")
            if ref_field and ref_field not in text:
                return (
                    f"Cross-reference for '{rule.field}' failed: "
                    f"referenced field '{ref_field}' not found"
                )

        return None

    # ------------------------------------------------------------------
    # Internal – export helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _export_pdf(html_text: str) -> bytes:
        """Convert HTML text to PDF via WeasyPrint."""
        from weasyprint import HTML  # type: ignore[import-untyped]

        return HTML(string=html_text).write_pdf()

    @staticmethod
    def _export_docx(text: str, metadata: DocumentMetadata) -> bytes:
        """Build a DOCX document from plain text with metadata."""
        from io import BytesIO

        from docx import Document  # type: ignore[import-untyped]

        doc = Document()
        doc.core_properties.author = metadata.author
        doc.core_properties.title = f"v{metadata.version}"
        doc.core_properties.comments = metadata.classification

        for line in text.split("\n"):
            doc.add_paragraph(line)

        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    @staticmethod
    def _export_xml(text: str) -> bytes:
        """Wrap text in an XML document element via lxml."""
        from lxml import etree  # type: ignore[import-untyped]

        root = etree.Element("document")
        content_el = etree.SubElement(root, "content")
        content_el.text = text
        return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")
