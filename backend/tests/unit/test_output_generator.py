"""Unit tests for OutputGenerator – rendering, validation, and export."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.encryption import EncryptionConfig
from app.models.templates import (
    DocumentMetadata,
    RenderedDocument,
    Template,
    ValidationRule,
)
from app.services.encryption_service import EncryptionService
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(**overrides) -> DocumentMetadata:
    defaults = {
        "author": "Test Author",
        "date": datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        "version": "1.0.0",
        "classification": "INTERNAL",
    }
    defaults.update(overrides)
    return DocumentMetadata(**defaults)


def _make_template(
    tmpdir: str,
    tpl_content: str = "Hello {{ name }}. Author: {{ metadata.author }}",
    fmt: str = "html",
    rules: list[ValidationRule] | None = None,
    encryption: EncryptionConfig | None = None,
    required_metadata: list[str] | None = None,
) -> Template:
    tpl_file = os.path.join(tmpdir, "test_template.html")
    with open(tpl_file, "w") as f:
        f.write(tpl_content)

    return Template(
        id="tpl-1",
        name="Test Template",
        format=fmt,
        structure={"sections": ["body"]},
        validation_rules=rules or [],
        required_metadata=required_metadata or ["author", "date", "version", "classification"],
        encryption_settings=encryption,
        jinja2_template_path=tpl_file,
    )


def _build_generator(registry: TemplateRegistry, encryption: EncryptionService | None = None) -> OutputGenerator:
    return OutputGenerator(registry=registry, encryption_service=encryption)


# ---------------------------------------------------------------------------
# render() tests
# ---------------------------------------------------------------------------

class TestRender:
    @pytest.mark.asyncio
    async def test_render_basic(self, tmp_path):
        """Render a simple Jinja2 template with data and metadata."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path))
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata(), session_id="s1")

        text = doc.content.decode("utf-8")
        assert "Hello World" in text
        assert "Test Author" in text
        assert doc.session_id == "s1"
        assert doc.template_id == "tpl-1"
        assert doc.format == "html"

    @pytest.mark.asyncio
    async def test_render_includes_all_metadata(self, tmp_path):
        """Rendered context should include author, date, version, classification."""
        tpl_content = (
            "author={{ metadata.author }} "
            "date={{ metadata.date }} "
            "version={{ metadata.version }} "
            "classification={{ metadata.classification }}"
        )
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), tpl_content=tpl_content)
        registry.register_template(tpl)

        meta = _make_metadata()
        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {}, meta)

        text = doc.content.decode("utf-8")
        assert "Test Author" in text
        assert "1.0.0" in text
        assert "INTERNAL" in text

    @pytest.mark.asyncio
    async def test_render_unknown_template_raises(self, tmp_path):
        """Requesting a non-existent template should raise ValueError."""
        registry = TemplateRegistry()
        gen = _build_generator(registry)

        with pytest.raises(ValueError, match="not found"):
            await gen.render("no-such-tpl", {}, _make_metadata())

    @pytest.mark.asyncio
    async def test_render_missing_jinja2_file_raises(self, tmp_path):
        """If the Jinja2 file doesn't exist on disk, raise FileNotFoundError."""
        registry = TemplateRegistry()
        tpl = Template(
            id="tpl-missing",
            name="Missing",
            format="html",
            structure={},
            validation_rules=[],
            required_metadata=[],
            encryption_settings=None,
            jinja2_template_path=os.path.join(str(tmp_path), "nonexistent.html"),
        )
        registry.register_template(tpl)

        gen = _build_generator(registry)
        with pytest.raises(FileNotFoundError):
            await gen.render("tpl-missing", {}, _make_metadata())

    @pytest.mark.asyncio
    async def test_render_with_encryption(self, tmp_path):
        """When encryption is enabled, rendered content should be encrypted."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        enc_config = EncryptionConfig(enabled=True, algorithm="Fernet", key_reference=key, target="output")

        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), encryption=enc_config)
        registry.register_template(tpl)

        enc_svc = EncryptionService()
        gen = _build_generator(registry, encryption=enc_svc)
        doc = await gen.render("tpl-1", {"name": "Secret"}, _make_metadata())

        # Content should NOT be plain text anymore.
        assert b"Hello Secret" not in doc.content

        # Decrypt to verify round-trip.
        decrypted = enc_svc.decrypt(doc.content, enc_config)
        assert b"Hello Secret" in decrypted


# ---------------------------------------------------------------------------
# validate() tests
# ---------------------------------------------------------------------------

class TestValidate:
    @pytest.mark.asyncio
    async def test_validate_no_rules(self, tmp_path):
        """A template with no rules should produce no violations."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=[])
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "OK"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert result == []

    @pytest.mark.asyncio
    async def test_validate_required_field_present(self, tmp_path):
        """Required field present in content → no violation."""
        rules = [ValidationRule(field="Hello", rule_type="required", parameters={})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert result == []

    @pytest.mark.asyncio
    async def test_validate_required_field_missing(self, tmp_path):
        """Required field missing from content → violation reported."""
        rules = [ValidationRule(field="MISSING_FIELD", rule_type="required", parameters={})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert len(result) == 1
        assert "MISSING_FIELD" in result[0]

    @pytest.mark.asyncio
    async def test_validate_regex_match(self, tmp_path):
        """Regex rule that matches → no violation."""
        rules = [ValidationRule(field="greeting", rule_type="regex", parameters={"pattern": r"Hello \w+"})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert result == []

    @pytest.mark.asyncio
    async def test_validate_regex_no_match(self, tmp_path):
        """Regex rule that doesn't match → violation reported."""
        rules = [ValidationRule(field="number", rule_type="regex", parameters={"pattern": r"^\d{10}$"})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert len(result) == 1
        assert "number" in result[0]

    @pytest.mark.asyncio
    async def test_validate_format_rule(self, tmp_path):
        """Format rule with expected value present → no violation."""
        rules = [ValidationRule(field="author_check", rule_type="format", parameters={"expected": "Test Author"})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "X"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert result == []

    @pytest.mark.asyncio
    async def test_validate_cross_reference_missing(self, tmp_path):
        """Cross-reference rule where referenced field is absent → violation."""
        rules = [ValidationRule(field="ref", rule_type="cross_reference", parameters={"reference_field": "NONEXISTENT_REF"})]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "X"}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert len(result) == 1
        assert "NONEXISTENT_REF" in result[0]

    @pytest.mark.asyncio
    async def test_validate_multiple_violations(self, tmp_path):
        """Multiple failing rules should all be reported."""
        rules = [
            ValidationRule(field="XYZFIELD1", rule_type="required", parameters={}),
            ValidationRule(field="XYZFIELD2", rule_type="required", parameters={}),
        ]
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), tpl_content="Nothing special here", rules=rules)
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {}, _make_metadata())
        result = await gen.validate(doc, tpl)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# export() tests
# ---------------------------------------------------------------------------

class TestExport:
    @pytest.mark.asyncio
    async def test_export_html(self, tmp_path):
        """HTML export returns UTF-8 encoded content."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), fmt="html")
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        exported = await gen.export(doc, "html")
        assert b"Hello World" in exported

    @pytest.mark.asyncio
    async def test_export_markdown(self, tmp_path):
        """Markdown export returns UTF-8 encoded content."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), fmt="md")
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())
        exported = await gen.export(doc, "md")
        assert b"Hello World" in exported

    @pytest.mark.asyncio
    async def test_export_pdf_calls_weasyprint(self, tmp_path):
        """PDF export delegates to WeasyPrint."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), fmt="html")
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())

        mock_html_cls = MagicMock()
        mock_html_cls.return_value.write_pdf.return_value = b"%PDF-fake"

        with patch("app.services.output_generator.OutputGenerator._export_pdf") as mock_pdf:
            mock_pdf.return_value = b"%PDF-fake"
            exported = await gen.export(doc, "pdf")

        assert isinstance(exported, bytes)
        assert exported == b"%PDF-fake"

    @pytest.mark.asyncio
    async def test_export_docx_calls_python_docx(self, tmp_path):
        """DOCX export delegates to python-docx."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), fmt="html")
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())

        with patch("app.services.output_generator.OutputGenerator._export_docx") as mock_docx:
            mock_docx.return_value = b"PK-fake-docx"
            exported = await gen.export(doc, "docx")

        assert isinstance(exported, bytes)
        assert exported == b"PK-fake-docx"

    @pytest.mark.asyncio
    async def test_export_xml_calls_lxml(self, tmp_path):
        """XML export delegates to lxml."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path), fmt="html")
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "World"}, _make_metadata())

        with patch("app.services.output_generator.OutputGenerator._export_xml") as mock_xml:
            mock_xml.return_value = b"<?xml version='1.0'?><document><content>test</content></document>"
            exported = await gen.export(doc, "xml")

        assert isinstance(exported, bytes)
        assert b"<document>" in exported

    @pytest.mark.asyncio
    async def test_export_unsupported_format_raises(self, tmp_path):
        """Requesting an unsupported format should raise ValueError."""
        registry = TemplateRegistry()
        tpl = _make_template(str(tmp_path))
        registry.register_template(tpl)

        gen = _build_generator(registry)
        doc = await gen.render("tpl-1", {"name": "X"}, _make_metadata())

        with pytest.raises(ValueError, match="Unsupported export format"):
            await gen.export(doc, "csv")
