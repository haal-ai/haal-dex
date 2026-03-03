"""Unit tests for TemplateRegistry."""

from __future__ import annotations

import pytest

from app.models.encryption import EncryptionConfig
from app.models.templates import Template, ValidationRule
from app.services.template_registry import TemplateSummary, TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(
    template_id: str = "tpl-1",
    name: str = "Report Template",
    fmt: str = "pdf",
    encryption: EncryptionConfig | None = None,
) -> Template:
    return Template(
        id=template_id,
        name=name,
        format=fmt,
        structure={"sections": ["intro", "body", "conclusion"]},
        validation_rules=[
            ValidationRule(field="title", rule_type="required", parameters={}),
        ],
        required_metadata=["author", "date", "version", "classification"],
        encryption_settings=encryption,
        jinja2_template_path=f"templates/{template_id}.j2",
    )


# ---------------------------------------------------------------------------
# register_template
# ---------------------------------------------------------------------------

class TestRegisterTemplate:
    def test_register_single_template(self) -> None:
        registry = TemplateRegistry()
        tpl = _make_template()
        registry.register_template(tpl)

        assert registry.get_template("tpl-1") is tpl

    def test_register_overwrites_existing(self) -> None:
        registry = TemplateRegistry()
        tpl_v1 = _make_template(name="V1")
        tpl_v2 = _make_template(name="V2")

        registry.register_template(tpl_v1)
        registry.register_template(tpl_v2)

        assert registry.get_template("tpl-1").name == "V2"

    def test_register_multiple_templates(self) -> None:
        registry = TemplateRegistry()
        tpl_a = _make_template(template_id="a", fmt="xml")
        tpl_b = _make_template(template_id="b", fmt="html")

        registry.register_template(tpl_a)
        registry.register_template(tpl_b)

        assert registry.get_template("a").format == "xml"
        assert registry.get_template("b").format == "html"


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------

class TestGetTemplate:
    def test_returns_correct_template(self) -> None:
        registry = TemplateRegistry()
        tpl = _make_template()
        registry.register_template(tpl)

        result = registry.get_template("tpl-1")
        assert result.id == "tpl-1"
        assert result.name == "Report Template"

    def test_raises_for_missing_template(self) -> None:
        registry = TemplateRegistry()

        with pytest.raises(ValueError, match="Template 'missing' not found"):
            registry.get_template("missing")

    def test_raises_for_empty_registry(self) -> None:
        registry = TemplateRegistry()

        with pytest.raises(ValueError):
            registry.get_template("any-id")


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------

class TestListTemplates:
    def test_empty_registry_returns_empty_list(self) -> None:
        registry = TemplateRegistry()
        assert registry.list_templates() == []

    def test_returns_all_registered_templates(self) -> None:
        registry = TemplateRegistry()
        for i in range(3):
            registry.register_template(
                _make_template(template_id=f"tpl-{i}", name=f"Template {i}")
            )

        summaries = registry.list_templates()
        assert len(summaries) == 3
        ids = {s.id for s in summaries}
        assert ids == {"tpl-0", "tpl-1", "tpl-2"}

    def test_summary_contains_expected_fields(self) -> None:
        registry = TemplateRegistry()
        tpl = _make_template(template_id="x", name="My Template", fmt="docx")
        registry.register_template(tpl)

        summaries = registry.list_templates()
        assert len(summaries) == 1
        s = summaries[0]
        assert isinstance(s, TemplateSummary)
        assert s.id == "x"
        assert s.name == "My Template"
        assert s.format == "docx"
        assert s.required_metadata == ["author", "date", "version", "classification"]


# ---------------------------------------------------------------------------
# Template fields preserved
# ---------------------------------------------------------------------------

class TestTemplateFieldsPreserved:
    """Verify that all template fields (format, structure, validation rules,
    required metadata, encryption settings) are stored and retrievable."""

    def test_all_fields_preserved(self) -> None:
        enc = EncryptionConfig(
            enabled=True,
            algorithm="AES-256-GCM",
            key_reference="key-output-1",
            target="output",
        )
        tpl = _make_template(encryption=enc)
        registry = TemplateRegistry()
        registry.register_template(tpl)

        result = registry.get_template(tpl.id)
        assert result.format == "pdf"
        assert result.structure == {"sections": ["intro", "body", "conclusion"]}
        assert len(result.validation_rules) == 1
        assert result.validation_rules[0].rule_type == "required"
        assert result.required_metadata == ["author", "date", "version", "classification"]
        assert result.encryption_settings is not None
        assert result.encryption_settings.algorithm == "AES-256-GCM"
        assert result.jinja2_template_path == "templates/tpl-1.j2"

    def test_template_without_encryption(self) -> None:
        tpl = _make_template(encryption=None)
        registry = TemplateRegistry()
        registry.register_template(tpl)

        result = registry.get_template(tpl.id)
        assert result.encryption_settings is None

    def test_supported_formats(self) -> None:
        """Templates can be registered for each supported output format."""
        registry = TemplateRegistry()
        for fmt in ("xml", "pdf", "docx", "md", "html"):
            tpl = _make_template(template_id=f"tpl-{fmt}", fmt=fmt)
            registry.register_template(tpl)

        for fmt in ("xml", "pdf", "docx", "md", "html"):
            assert registry.get_template(f"tpl-{fmt}").format == fmt
