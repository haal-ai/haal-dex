from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.models.templates import Template
from app.services.template_registry import TemplateRegistry


@lru_cache
def get_default_template_registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    base_dir = Path(__file__).resolve().parents[1] / "templates"

    registry.register_template(
        Template(
            id="demo-html-report",
            name="Demo HTML Report",
            format="html",
            structure={},
            validation_rules=[],
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(base_dir / "demo_html_report.j2"),
        )
    )

    registry.register_template(
        Template(
            id="demo-slide-outline",
            name="Demo Slide Outline",
            format="md",
            structure={},
            validation_rules=[],
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(base_dir / "demo_slide_outline.j2"),
        )
    )

    registry.register_template(
        Template(
            id="demo-md-report",
            name="Demo Markdown Report",
            format="md",
            structure={},
            validation_rules=[],
            required_metadata=["author", "date", "version", "classification"],
            encryption_settings=None,
            jinja2_template_path=str(base_dir / "demo_md_report.j2"),
        )
    )

    return registry
