"""Environment data injection into personality system prompts.

Loads external data from file paths (.txt, .json, .yaml) and environment
variable references ($VAR_NAME), then appends the loaded content to the
system prompt as structured context sections.  Missing or unparseable
sources are logged as warnings and skipped — they never prevent the
session from starting.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class EnvironmentInjector:
    """Loads environment data sources and injects into system prompt."""

    def inject(
        self, system_prompt: str, data_sources: list[str], base_dir: Path
    ) -> str:
        """Read all data sources and append to system prompt.

        Supports: file paths (.txt, .json, .yaml), env var refs ($VAR_NAME).
        Logs warnings for missing/unparseable sources, continues without them.

        Args:
            system_prompt: The original personality system prompt.
            data_sources: List of file paths or ``$VAR_NAME`` references.
            base_dir: Base directory for resolving relative file paths.

        Returns:
            The system prompt with loaded data appended as structured
            context sections.  When *data_sources* is empty the original
            prompt is returned unchanged.
        """
        if not data_sources:
            return system_prompt

        sections: list[str] = []
        for source in data_sources:
            content = self._load_source(source, base_dir)
            if content is not None:
                sections.append(content)

        if not sections:
            return system_prompt

        context_block = "\n\n".join(sections)
        return (
            f"{system_prompt}\n\n"
            f"--- Environment Context ---\n"
            f"{context_block}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_source(self, source: str, base_dir: Path) -> str | None:
        """Load a single data source, returning ``None`` on failure."""
        if source.startswith("$"):
            return self._load_env_var(source)
        return self._load_file(source, base_dir)

    def _load_env_var(self, source: str) -> str | None:
        """Read an environment variable reference like ``$VAR_NAME``."""
        var_name = source[1:]  # strip leading '$'
        value = os.environ.get(var_name)
        if value is None:
            logger.warning(
                "Environment variable '%s' is not set — skipping", var_name
            )
            return None
        return f"[env:{var_name}]\n{value}"

    def _load_file(self, source: str, base_dir: Path) -> str | None:
        """Read and parse a file (.txt, .json, .yaml/.yml)."""
        path = Path(source)
        if not path.is_absolute():
            path = base_dir / path

        if not path.exists():
            logger.warning(
                "Environment data source file does not exist: %s — skipping",
                path,
            )
            return None

        suffix = path.suffix.lower()
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            logger.warning(
                "Failed to read environment data source file: %s — skipping",
                path,
                exc_info=True,
            )
            return None

        if suffix in (".yaml", ".yml"):
            return self._parse_yaml(raw, path)
        if suffix == ".json":
            return self._parse_json(raw, path)
        # .txt and any other extension — return raw content
        return f"[file:{path.name}]\n{raw}"

    def _parse_yaml(self, raw: str, path: Path) -> str | None:
        """Parse YAML content, returning a formatted section or ``None``."""
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            logger.warning(
                "Failed to parse YAML file %s: %s — skipping", path, exc
            )
            return None
        return f"[file:{path.name}]\n{self._format_data(data)}"

    def _parse_json(self, raw: str, path: Path) -> str | None:
        """Parse JSON content, returning a formatted section or ``None``."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Failed to parse JSON file %s: %s — skipping", path, exc
            )
            return None
        return f"[file:{path.name}]\n{self._format_data(data)}"

    @staticmethod
    def _format_data(data: object) -> str:
        """Format parsed structured data as a readable string."""
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2, ensure_ascii=False)
