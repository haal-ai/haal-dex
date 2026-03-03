"""Pipeline configuration parser and serializer.

Handles conversion between raw YAML/JSON strings and PipelineConfig dataclass
instances, with descriptive error reporting for invalid configurations.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import yaml

from app.models.pipeline import (
    AgentConfig,
    OAuthConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)


class ConfigParseError(Exception):
    """Raised when a pipeline config cannot be parsed.

    Attributes:
        message: Human-readable description of the error.
        location: Where in the config the error occurred (line/col or key path).
        nature: Category of the failure (syntax, missing_field, invalid_type, etc.).
    """

    def __init__(self, message: str, location: str | None = None, nature: str = "parse_error"):
        self.message = message
        self.location = location
        self.nature = nature
        super().__init__(message)


def parse_config(raw: str, format: str) -> PipelineConfig:
    """Parse a raw YAML or JSON string into a PipelineConfig.

    Args:
        raw: The raw configuration string.
        format: Either "yaml" or "json".

    Returns:
        A PipelineConfig instance.

    Raises:
        ConfigParseError: If the config is invalid, with location and nature details.
        ValueError: If format is not "yaml" or "json".
    """
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format: {format!r}. Must be 'yaml' or 'json'.")

    data = _parse_raw(raw, format)
    return _dict_to_pipeline_config(data, format)


def serialize_config(config: PipelineConfig, format: str) -> str:
    """Serialize a PipelineConfig to a YAML or JSON string.

    Args:
        config: The PipelineConfig instance to serialize.
        format: Either "yaml" or "json".

    Returns:
        The serialized configuration string.

    Raises:
        ValueError: If format is not "yaml" or "json".
    """
    if format not in ("yaml", "json"):
        raise ValueError(f"Unsupported format: {format!r}. Must be 'yaml' or 'json'.")

    data = asdict(config)
    # Strip None values from nested dicts for cleaner output
    data = _strip_none(data)

    if format == "yaml":
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    else:
        return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_raw(raw: str, format: str) -> dict[str, Any]:
    """Parse raw string into a dict, raising ConfigParseError on syntax errors."""
    if format == "yaml":
        return _parse_yaml(raw)
    else:
        return _parse_json(raw)


def _parse_yaml(raw: str) -> dict[str, Any]:
    """Parse YAML with line/column error reporting."""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        location = None
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            mark = exc.problem_mark
            location = f"line {mark.line + 1}, column {mark.column + 1}"
        raise ConfigParseError(
            message=f"YAML syntax error: {exc}",
            location=location,
            nature="syntax",
        ) from exc

    if not isinstance(data, dict):
        raise ConfigParseError(
            message="YAML config must be a mapping at the top level",
            location="root",
            nature="invalid_type",
        )
    return data


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse JSON with line/column error reporting."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        location = f"line {exc.lineno}, column {exc.colno}"
        raise ConfigParseError(
            message=f"JSON syntax error: {exc.msg}",
            location=location,
            nature="syntax",
        ) from exc

    if not isinstance(data, dict):
        raise ConfigParseError(
            message="JSON config must be an object at the top level",
            location="root",
            nature="invalid_type",
        )
    return data


def _dict_to_pipeline_config(data: dict[str, Any], format: str) -> PipelineConfig:
    """Convert a parsed dict into a PipelineConfig, with descriptive errors."""
    _require_field(data, "name", "root", format)
    _require_field(data, "agents", "root", format)
    _require_field(data, "output", "root", format)

    if not isinstance(data["agents"], list):
        raise ConfigParseError(
            message="'agents' must be a list",
            location=_key_path("agents", format),
            nature="invalid_type",
        )

    agents = []
    for i, agent_data in enumerate(data["agents"]):
        if not isinstance(agent_data, dict):
            raise ConfigParseError(
                message=f"Agent at index {i} must be a mapping",
                location=_key_path(f"agents[{i}]", format),
                nature="invalid_type",
            )
        agents.append(_dict_to_agent_config(agent_data, i, format))

    if not isinstance(data["output"], dict):
        raise ConfigParseError(
            message="'output' must be a mapping",
            location=_key_path("output", format),
            nature="invalid_type",
        )
    output = _dict_to_output_config(data["output"], format)

    execution_timeout = data.get("execution_timeout", 600)
    if not isinstance(execution_timeout, (int, float)):
        raise ConfigParseError(
            message="'execution_timeout' must be a number",
            location=_key_path("execution_timeout", format),
            nature="invalid_type",
        )

    return PipelineConfig(
        name=data["name"],
        agents=agents,
        output=output,
        execution_timeout=int(execution_timeout),
    )


def _dict_to_agent_config(data: dict[str, Any], index: int, format: str) -> AgentConfig:
    """Convert a dict to AgentConfig."""
    prefix = f"agents[{index}]"
    _require_field(data, "name", prefix, format)
    _require_field(data, "model", prefix, format)
    _require_field(data, "provider_config", prefix, format)
    _require_field(data, "description", prefix, format)

    if not isinstance(data["provider_config"], dict):
        raise ConfigParseError(
            message=f"'provider_config' in agent '{data.get('name', index)}' must be a mapping",
            location=_key_path(f"{prefix}.provider_config", format),
            nature="invalid_type",
        )

    provider_config = _dict_to_provider_config(
        data["provider_config"], index, data.get("name", str(index)), format
    )

    return AgentConfig(
        name=data["name"],
        model=data["model"],
        provider_config=provider_config,
        description=data["description"],
        system_prompt=data.get("system_prompt"),
        faiss_indexes=data.get("faiss_indexes", []),
        tools=data.get("tools", []),
        template=data.get("template"),
    )


def _dict_to_provider_config(
    data: dict[str, Any], agent_index: int, agent_name: str, format: str
) -> ProviderConfig:
    """Convert a dict to ProviderConfig."""
    prefix = f"agents[{agent_index}].provider_config"
    _require_field(data, "provider_type", prefix, format)
    _require_field(data, "model_id", prefix, format)

    oauth_config = None
    if "oauth_config" in data and data["oauth_config"] is not None:
        if not isinstance(data["oauth_config"], dict):
            raise ConfigParseError(
                message=f"'oauth_config' in agent '{agent_name}' provider_config must be a mapping",
                location=_key_path(f"{prefix}.oauth_config", format),
                nature="invalid_type",
            )
        oauth_config = _dict_to_oauth_config(
            data["oauth_config"], agent_index, agent_name, format
        )

    return ProviderConfig(
        provider_type=data["provider_type"],
        model_id=data["model_id"],
        inference_profile_id=data.get("inference_profile_id"),
        endpoint=data.get("endpoint"),
        api_key=data.get("api_key"),
        region=data.get("region"),
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 2048),
        oauth_config=oauth_config,
    )


def _dict_to_oauth_config(
    data: dict[str, Any], agent_index: int, agent_name: str, format: str
) -> OAuthConfig:
    """Convert a dict to OAuthConfig."""
    prefix = f"agents[{agent_index}].provider_config.oauth_config"
    _require_field(data, "client_id", prefix, format)
    _require_field(data, "client_secret", prefix, format)
    _require_field(data, "token_url", prefix, format)
    _require_field(data, "scopes", prefix, format)

    return OAuthConfig(
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        token_url=data["token_url"],
        scopes=data["scopes"],
    )


def _dict_to_output_config(data: dict[str, Any], format: str) -> OutputConfig:
    """Convert a dict to OutputConfig."""
    _require_field(data, "template", "output", format)
    _require_field(data, "formats", "output", format)

    if not isinstance(data["formats"], list):
        raise ConfigParseError(
            message="'formats' in output must be a list",
            location=_key_path("output.formats", format),
            nature="invalid_type",
        )

    return OutputConfig(
        template=data["template"],
        formats=data["formats"],
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _require_field(data: dict, field: str, parent_path: str, format: str) -> None:
    """Raise ConfigParseError if a required field is missing."""
    if field not in data:
        raise ConfigParseError(
            message=f"Missing required field '{field}' in {parent_path}",
            location=_key_path(f"{parent_path}.{field}" if parent_path != "root" else field, format),
            nature="missing_field",
        )


def _key_path(path: str, format: str) -> str:
    """Return a human-readable location string for the given key path."""
    return f"key path: {path}"


def _strip_none(obj: Any) -> Any:
    """Recursively remove keys with None values from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(item) for item in obj]
    return obj
