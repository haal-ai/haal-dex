# Feature: intent, Property 14: Template completeness
# Feature: intent, Property 15: Jinja2 template rendering produces output
# Feature: intent, Property 16: Validation failure reports violated rules
# Feature: intent, Property 17: Export format matches request
"""Property tests for templates and output generation.

Property 14: Template completeness — Every template contains format, structure,
validation rules, metadata; every document has author/date/version/classification.
**Validates: Requirements 7.1, 7.5**

Property 15: Jinja2 template rendering produces output — For valid template and
data, render produces non-empty document.
**Validates: Requirements 7.3**

Property 16: Validation failure reports violated rules — For documents violating
rules, report exactly which rules were violated.
**Validates: Requirements 7.4**

Property 17: Export format matches request — For any valid session and format
(PDF/XML/DOCX), export produces document in requested format.
**Validates: Requirements 8.3**
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

from app.models.templates import (
    DocumentMetadata,
    RenderedDocument,
    Template,
    ValidationRule,
)
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_formats = st.sampled_from(["xml", "pdf", "docx", "md", "html"])

_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)

_metadata_strategy = st.builds(
    DocumentMetadata,
    author=_non_empty_text,
    date=st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    ),
    version=st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
    classification=st.sampled_from(["public", "internal", "confidential", "secret"]),
)


_structure_strategy = st.dictionaries(
    keys=_non_empty_text,
    values=_non_empty_text,
    min_size=1,
    max_size=5,
)

_validation_rule_strategy = st.builds(
    ValidationRule,
    field=_non_empty_text,
    rule_type=st.sampled_from(["required", "format", "cross_reference", "regex"]),
    parameters=st.just({}),
)


@st.composite
def template_strategy(draw):
    """Draw a valid Template with all required fields."""
    fmt = draw(_formats)
    return Template(
        id=str(uuid.uuid4()),
        name=draw(_non_empty_text),
        format=fmt,
        structure=draw(_structure_strategy),
        validation_rules=draw(st.lists(_validation_rule_strategy, min_size=0, max_size=3)),
        required_metadata=["author", "date", "version", "classification"],
        encryption_settings=None,
        jinja2_template_path="placeholder.html",  # overridden in render tests
    )


# ---------------------------------------------------------------------------
# Property 14: Template completeness
# ---------------------------------------------------------------------------


@given(template=template_strategy())
@settings(max_examples=100, deadline=None)
def test_template_completeness(template: Template):
    """Property 14: Every template contains format, structure, validation rules,
    metadata; every document has author/date/version/classification.

    **Validates: Requirements 7.1, 7.5**
    """
    # Template must have all required fields
    assert template.format is not None and template.format != "", (
        "Template must have a format"
    )
    assert template.structure is not None and len(template.structure) > 0, (
        "Template must have a structure"
    )
    assert template.validation_rules is not None, (
        "Template must have validation_rules (may be empty list)"
    )
    assert template.required_metadata is not None and len(template.required_metadata) > 0, (
        "Template must have required_metadata"
    )
    # Required metadata must include the four mandatory fields
    required_fields = {"author", "date", "version", "classification"}
    assert required_fields.issubset(set(template.required_metadata)), (
        f"Template required_metadata must include {required_fields}, "
        f"got {template.required_metadata}"
    )


@given(metadata=_metadata_strategy)
@settings(max_examples=100, deadline=None)
def test_document_metadata_completeness(metadata: DocumentMetadata):
    """Property 14 (document part): Every document has author/date/version/classification.

    **Validates: Requirements 7.1, 7.5**
    """
    assert metadata.author is not None and metadata.author != "", (
        "Document metadata must have an author"
    )
    assert metadata.date is not None, "Document metadata must have a date"
    assert metadata.version is not None and metadata.version != "", (
        "Document metadata must have a version"
    )
    assert metadata.classification is not None and metadata.classification != "", (
        "Document metadata must have a classification"
    )


# ---------------------------------------------------------------------------
# Property 15: Jinja2 template rendering produces output
# ---------------------------------------------------------------------------


@given(
    data=st.dictionaries(
        keys=st.from_regex(r"[a-z][a-z0-9_]{0,9}", fullmatch=True),
        values=_non_empty_text,
        min_size=1,
        max_size=5,
    ),
    metadata=_metadata_strategy,
)
@settings(max_examples=100, deadline=None)
def test_jinja2_rendering_produces_non_empty_output(data: dict, metadata: DocumentMetadata):
    """Property 15: For valid template and data, render produces non-empty document.

    **Validates: Requirements 7.3**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple Jinja2 template that renders all data keys
        tpl_content = "<html><body>"
        tpl_content += "{% for key, val in data.items() %}"
        tpl_content += "<p>{{ key }}: {{ val }}</p>"
        tpl_content += "{% endfor %}"
        tpl_content += "<p>Author: {{ metadata.author }}</p>"
        tpl_content += "<p>Date: {{ metadata.date }}</p>"
        tpl_content += "<p>Version: {{ metadata.version }}</p>"
        tpl_content += "<p>Classification: {{ metadata.classification }}</p>"
        tpl_content += "</body></html>"

        tpl_path = Path(tmpdir) / "test_template.html"
        tpl_path.write_text(tpl_content)

        template = Template(
            id="test-tpl",
            name="Test Template",
            format="html",
            structure={"body": "content"},
            validation_rules=[],
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(tpl_path),
        )

        registry = TemplateRegistry()
        registry.register_template(template)
        generator = OutputGenerator(registry=registry)

        # Wrap data under a "data" key so the template can iterate
        render_data = {"data": data}
        doc = asyncio.run(
            generator.render(
                template_id="test-tpl",
                data=render_data,
                metadata=metadata,
                session_id="test-session",
            )
        )

        assert doc.content is not None and len(doc.content) > 0, (
            "Rendered document content must be non-empty"
        )
        assert doc.metadata == metadata, "Rendered document must preserve metadata"


# ---------------------------------------------------------------------------
# Property 16: Validation failure reports violated rules
# ---------------------------------------------------------------------------


@given(
    field_names=st.lists(
        st.from_regex(r"[a-z][a-z0-9_]{2,10}", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    metadata=_metadata_strategy,
)
@settings(max_examples=100, deadline=None)
def test_validation_failure_reports_violated_rules(
    field_names: list[str], metadata: DocumentMetadata
):
    """Property 16: For documents violating rules, report exactly which rules
    were violated.

    **Validates: Requirements 7.4**

    Strategy: Create a template with "required" rules for random field names,
    render a document that does NOT contain those fields, then verify the
    validation result reports exactly those missing fields.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Minimal template that does NOT include the required field names
        tpl_path = Path(tmpdir) / "minimal.html"
        tpl_path.write_text("<html><body>Empty doc</body></html>")

        rules = [
            ValidationRule(field=name, rule_type="required", parameters={})
            for name in field_names
        ]

        template = Template(
            id="val-tpl",
            name="Validation Template",
            format="html",
            structure={"body": "content"},
            validation_rules=rules,
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(tpl_path),
        )

        registry = TemplateRegistry()
        registry.register_template(template)
        generator = OutputGenerator(registry=registry)

        doc = asyncio.run(
            generator.render(
                template_id="val-tpl",
                data={},
                metadata=metadata,
                session_id="test-session",
            )
        )

        # The validation result should report violations for each missing field
        violations = doc.validation_result
        assert len(violations) == len(field_names), (
            f"Expected {len(field_names)} violations, got {len(violations)}: {violations}"
        )

        # Each field name should appear in exactly one violation message
        for name in field_names:
            matching = [v for v in violations if name in v]
            assert len(matching) >= 1, (
                f"Expected violation for field '{name}' but none found in: {violations}"
            )


# ---------------------------------------------------------------------------
# Property 17: Export format matches request
# ---------------------------------------------------------------------------


@given(
    fmt=st.sampled_from(["pdf", "xml", "docx"]),
    metadata=_metadata_strategy,
)
@settings(max_examples=100, deadline=None)
def test_export_format_matches_request(fmt: str, metadata: DocumentMetadata):
    """Property 17: For any valid session and format (PDF/XML/DOCX), export
    produces document in requested format.

    **Validates: Requirements 8.3**

    Strategy: Mock the internal export methods (_export_pdf, _export_docx,
    _export_xml) to return known bytes, then verify export returns non-empty
    bytes for each format.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tpl_path = Path(tmpdir) / "export_tpl.html"
        tpl_path.write_text("<html><body>Export test</body></html>")

        template = Template(
            id="export-tpl",
            name="Export Template",
            format="html",
            structure={"body": "content"},
            validation_rules=[],
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(tpl_path),
        )

        registry = TemplateRegistry()
        registry.register_template(template)
        generator = OutputGenerator(registry=registry)

        # First render a document
        doc = asyncio.run(
            generator.render(
                template_id="export-tpl",
                data={},
                metadata=metadata,
                session_id="test-session",
            )
        )

        # Mock the export methods to return known bytes
        mock_pdf_bytes = b"%PDF-1.4 mock pdf content"
        mock_docx_bytes = b"PK\x03\x04 mock docx content"
        mock_xml_bytes = b"<?xml version='1.0'?><document>mock</document>"

        with (
            patch.object(
                OutputGenerator, "_export_pdf", return_value=mock_pdf_bytes
            ),
            patch.object(
                OutputGenerator, "_export_docx", return_value=mock_docx_bytes
            ),
            patch.object(
                OutputGenerator, "_export_xml", return_value=mock_xml_bytes
            ),
        ):
            result = asyncio.run(generator.export(doc, fmt))

        assert isinstance(result, bytes), (
            f"Export for format '{fmt}' must return bytes, got {type(result)}"
        )
        assert len(result) > 0, (
            f"Export for format '{fmt}' must return non-empty bytes"
        )

        # Verify the correct mock was called based on format
        if fmt == "pdf":
            assert result == mock_pdf_bytes
        elif fmt == "docx":
            assert result == mock_docx_bytes
        elif fmt == "xml":
            assert result == mock_xml_bytes
