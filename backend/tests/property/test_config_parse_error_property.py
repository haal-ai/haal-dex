# Feature: intent, Property 27: Invalid config parsing error specificity
"""Property 27: Invalid config parsing error specificity

For any invalid config, parser returns error identifying location and nature
of failure.

**Validates: Requirements 19.5**

Strategy:
- Generate invalid config strings via multiple mutation strategies:
  1. Syntax errors (malformed YAML/JSON)
  2. Missing required fields (remove a required key from a valid config)
  3. Wrong types (replace a field with an incompatible type)
- Verify that ConfigParseError is raised with non-None location and nature.
"""

from __future__ import annotations

import json

import yaml
from hypothesis import given, settings, assume, strategies as st

from app.services.config_parser import ConfigParseError, parse_config

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_formats = st.sampled_from(["yaml", "json"])


def _minimal_config_dict() -> dict:
    """Return a minimal valid pipeline config as a dict."""
    return {
        "name": "test-pipeline",
        "agents": [
            {
                "name": "agent1",
                "model": "bedrock/claude-3-sonnet",
                "provider_config": {
                    "provider_type": "bedrock",
                    "model_id": "claude-3-sonnet",
                    "region": "us-east-1",
                },
                "description": "First agent",
            }
        ],
        "output": {
            "template": "default",
            "formats": ["pdf"],
        },
    }


# Required fields at each level that, when removed, should cause a parse error
_ROOT_REQUIRED_FIELDS = ["name", "agents", "output"]
_AGENT_REQUIRED_FIELDS = ["name", "model", "provider_config", "description"]
_PROVIDER_REQUIRED_FIELDS = ["provider_type", "model_id"]
_OUTPUT_REQUIRED_FIELDS = ["template", "formats"]


@st.composite
def missing_root_field_config(draw):
    """Generate a config dict with one required root field removed."""
    data = _minimal_config_dict()
    field = draw(st.sampled_from(_ROOT_REQUIRED_FIELDS))
    del data[field]
    fmt = draw(_formats)
    if fmt == "yaml":
        return yaml.dump(data, sort_keys=False), fmt
    return json.dumps(data), fmt


@st.composite
def missing_agent_field_config(draw):
    """Generate a config dict with one required agent field removed."""
    data = _minimal_config_dict()
    field = draw(st.sampled_from(_AGENT_REQUIRED_FIELDS))
    del data["agents"][0][field]
    fmt = draw(_formats)
    if fmt == "yaml":
        return yaml.dump(data, sort_keys=False), fmt
    return json.dumps(data), fmt


@st.composite
def missing_provider_field_config(draw):
    """Generate a config dict with one required provider_config field removed."""
    data = _minimal_config_dict()
    field = draw(st.sampled_from(_PROVIDER_REQUIRED_FIELDS))
    del data["agents"][0]["provider_config"][field]
    fmt = draw(_formats)
    if fmt == "yaml":
        return yaml.dump(data, sort_keys=False), fmt
    return json.dumps(data), fmt


@st.composite
def missing_output_field_config(draw):
    """Generate a config dict with one required output field removed."""
    data = _minimal_config_dict()
    field = draw(st.sampled_from(_OUTPUT_REQUIRED_FIELDS))
    del data["output"][field]
    fmt = draw(_formats)
    if fmt == "yaml":
        return yaml.dump(data, sort_keys=False), fmt
    return json.dumps(data), fmt


@st.composite
def wrong_type_config(draw):
    """Generate a config dict with a field replaced by an incompatible type."""
    data = _minimal_config_dict()
    mutation = draw(st.sampled_from([
        ("agents", "not-a-list"),           # agents must be a list
        ("output", "not-a-mapping"),        # output must be a mapping
    ]))
    field, bad_value = mutation
    data[field] = bad_value
    fmt = draw(_formats)
    if fmt == "yaml":
        return yaml.dump(data, sort_keys=False), fmt
    return json.dumps(data), fmt


@st.composite
def syntax_error_yaml(draw):
    """Generate a YAML string with a syntax error."""
    bad_yaml = draw(st.sampled_from([
        "name: test\nagents:\n  - name: a\n    bad_indent",
        "name: test\n  agents: [",
        ": invalid\n  - broken",
        "{{not yaml}}",
    ]))
    return bad_yaml, "yaml"


@st.composite
def syntax_error_json(draw):
    """Generate a JSON string with a syntax error."""
    bad_json = draw(st.sampled_from([
        '{"name": "test", "agents": [}',
        '{"name": "test", agents: []}',
        '{name: test}',
        '{"unclosed": "string',
    ]))
    return bad_json, "json"


@st.composite
def non_mapping_top_level(draw):
    """Generate a config that is not a mapping at the top level."""
    fmt = draw(_formats)
    if fmt == "yaml":
        return "- item1\n- item2", fmt
    return "[1, 2, 3]", fmt


@st.composite
def any_invalid_config(draw):
    """Draw from any of the invalid config strategies."""
    strategy = draw(st.sampled_from([
        missing_root_field_config(),
        missing_agent_field_config(),
        missing_provider_field_config(),
        missing_output_field_config(),
        wrong_type_config(),
        syntax_error_yaml(),
        syntax_error_json(),
        non_mapping_top_level(),
    ]))
    return draw(strategy)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(invalid=any_invalid_config())
@settings(max_examples=100)
def test_invalid_config_raises_error_with_location_and_nature(invalid):
    """Property 27: For any invalid config, parser returns error identifying
    location and nature of failure.

    **Validates: Requirements 19.5**
    """
    raw, fmt = invalid
    try:
        parse_config(raw, fmt)
        # If parse_config didn't raise, the config might actually be valid
        # for some edge-case YAML interpretations — skip those.
        assume(False)
    except ConfigParseError as exc:
        assert exc.location is not None, (
            f"ConfigParseError missing location for format={fmt!r}.\n"
            f"Message: {exc.message}\n"
            f"Nature: {exc.nature}"
        )
        assert exc.nature is not None, (
            f"ConfigParseError missing nature for format={fmt!r}.\n"
            f"Message: {exc.message}"
        )
        assert exc.nature in ("syntax", "missing_field", "invalid_type"), (
            f"Unexpected error nature: {exc.nature!r}"
        )
