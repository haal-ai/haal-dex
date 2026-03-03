"""Template registry for managing output document templates.

Provides an in-memory store of ``Template`` objects keyed by template ID.
Templates define output format, document structure, validation rules,
required metadata, and optional encryption settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.templates import Template


@dataclass
class TemplateSummary:
    """Lightweight summary of a template for listing."""

    id: str
    name: str
    format: str
    required_metadata: list[str]


class TemplateRegistry:
    """In-memory registry of output document templates.

    Stores templates keyed by their ``id`` and exposes methods to
    register, retrieve, and list templates.
    """

    def __init__(self) -> None:
        self._templates: dict[str, Template] = {}

    def register_template(self, template: Template) -> None:
        """Add a template to the registry.

        Overwrites any existing template with the same ``id``.
        """
        self._templates[template.id] = template

    def get_template(self, template_id: str) -> Template:
        """Return the template with the given *template_id*.

        Raises ``ValueError`` if no template with that ID is registered.
        """
        template = self._templates.get(template_id)
        if template is None:
            raise ValueError(f"Template '{template_id}' not found")
        return template

    def list_templates(self) -> list[TemplateSummary]:
        """Return summaries of all registered templates."""
        return [
            TemplateSummary(
                id=t.id,
                name=t.name,
                format=t.format,
                required_metadata=t.required_metadata,
            )
            for t in self._templates.values()
        ]
