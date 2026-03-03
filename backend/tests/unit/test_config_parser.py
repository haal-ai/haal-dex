"""Unit tests for the PipelineConfig parser and serializer."""

import json

import pytest
import yaml

from app.models.pipeline import (
    AgentConfig,
    OAuthConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.services.config_parser import (
    ConfigParseError,
    parse_config,
    serialize_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _full_config_dict() -> dict:
    """Return a fully-populated pipeline config dict."""
    return {
        "name": "full-pipeline",
        "agents": [
            {
                "name": "analyzer",
                "model": "bedrock/claude-3-sonnet",
                "provider_config": {
                    "provider_type": "bedrock",
                    "model_id": "claude-3-sonnet",
                    "region": "us-east-1",
                    "temperature": 0.5,
                    "max_tokens": 4096,
                },
                "description": "Analyzes input",
                "system_prompt": "You are an analyzer.",
                "faiss_indexes": [0, 1],
                "tools": ["read", "write"],
                "template": "analysis-template",
            },
            {
                "name": "copilot-agent",
                "model": "github/copilot",
                "provider_config": {
                    "provider_type": "github_copilot",
                    "model_id": "copilot-chat",
                    "oauth_config": {
                        "client_id": "cid",
                        "client_secret": "csecret",
                        "token_url": "https://github.com/login/oauth/access_token",
                        "scopes": ["read", "write"],
                    },
                },
                "description": "Copilot agent",
            },
        ],
        "output": {
            "template": "report",
            "formats": ["pdf", "docx", "xml"],
        },
        "execution_timeout": 300,
    }


# ---------------------------------------------------------------------------
# parse_config — YAML
# ---------------------------------------------------------------------------


class TestParseYAML:
    def test_minimal_yaml(self):
        raw = yaml.dump(_minimal_config_dict(), sort_keys=False)
        config = parse_config(raw, "yaml")
        assert config.name == "test-pipeline"
        assert len(config.agents) == 1
        assert config.agents[0].name == "agent1"
        assert config.output.template == "default"
        assert config.execution_timeout == 600  # default

    def test_full_yaml(self):
        raw = yaml.dump(_full_config_dict(), sort_keys=False)
        config = parse_config(raw, "yaml")
        assert config.name == "full-pipeline"
        assert len(config.agents) == 2
        assert config.agents[0].faiss_indexes == [0, 1]
        assert config.agents[0].tools == ["read", "write"]
        assert config.agents[1].provider_config.oauth_config is not None
        assert config.agents[1].provider_config.oauth_config.client_id == "cid"
        assert config.execution_timeout == 300

    def test_yaml_syntax_error_reports_location(self):
        raw = "name: test\nagents:\n  - name: a\n    bad_indent"
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(raw, "yaml")
        assert exc_info.value.nature == "syntax"
        assert exc_info.value.location is not None
        assert "line" in exc_info.value.location

    def test_yaml_non_mapping_top_level(self):
        raw = "- item1\n- item2"
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(raw, "yaml")
        assert exc_info.value.nature == "invalid_type"


# ---------------------------------------------------------------------------
# parse_config — JSON
# ---------------------------------------------------------------------------


class TestParseJSON:
    def test_minimal_json(self):
        raw = json.dumps(_minimal_config_dict())
        config = parse_config(raw, "json")
        assert config.name == "test-pipeline"
        assert len(config.agents) == 1

    def test_full_json(self):
        raw = json.dumps(_full_config_dict())
        config = parse_config(raw, "json")
        assert config.name == "full-pipeline"
        assert config.agents[1].provider_config.oauth_config.scopes == ["read", "write"]

    def test_json_syntax_error_reports_location(self):
        raw = '{"name": "test", "agents": [}'
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(raw, "json")
        assert exc_info.value.nature == "syntax"
        assert "line" in exc_info.value.location

    def test_json_non_object_top_level(self):
        raw = "[1, 2, 3]"
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(raw, "json")
        assert exc_info.value.nature == "invalid_type"


# ---------------------------------------------------------------------------
# parse_config — missing / invalid fields
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_missing_name(self):
        data = _minimal_config_dict()
        del data["name"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "name" in exc_info.value.message
        assert exc_info.value.nature == "missing_field"

    def test_missing_agents(self):
        data = _minimal_config_dict()
        del data["agents"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "agents" in exc_info.value.message

    def test_missing_output(self):
        data = _minimal_config_dict()
        del data["output"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "output" in exc_info.value.message

    def test_agents_not_a_list(self):
        data = _minimal_config_dict()
        data["agents"] = "not-a-list"
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert exc_info.value.nature == "invalid_type"

    def test_agent_missing_provider_config(self):
        data = _minimal_config_dict()
        del data["agents"][0]["provider_config"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "provider_config" in exc_info.value.message
        assert exc_info.value.nature == "missing_field"

    def test_agent_missing_description(self):
        data = _minimal_config_dict()
        del data["agents"][0]["description"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "description" in exc_info.value.message

    def test_provider_config_missing_provider_type(self):
        data = _minimal_config_dict()
        del data["agents"][0]["provider_config"]["provider_type"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "provider_type" in exc_info.value.message

    def test_output_missing_template(self):
        data = _minimal_config_dict()
        del data["output"]["template"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "template" in exc_info.value.message

    def test_output_formats_not_a_list(self):
        data = _minimal_config_dict()
        data["output"]["formats"] = "pdf"
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert exc_info.value.nature == "invalid_type"

    def test_oauth_config_missing_fields(self):
        data = _full_config_dict()
        del data["agents"][1]["provider_config"]["oauth_config"]["client_id"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert "client_id" in exc_info.value.message

    def test_error_has_location(self):
        """All ConfigParseErrors should include a location."""
        data = _minimal_config_dict()
        del data["name"]
        with pytest.raises(ConfigParseError) as exc_info:
            parse_config(json.dumps(data), "json")
        assert exc_info.value.location is not None


# ---------------------------------------------------------------------------
# serialize_config
# ---------------------------------------------------------------------------


class TestSerialize:
    def test_serialize_yaml(self):
        config = parse_config(json.dumps(_minimal_config_dict()), "json")
        result = serialize_config(config, "yaml")
        assert isinstance(result, str)
        parsed_back = yaml.safe_load(result)
        assert parsed_back["name"] == "test-pipeline"

    def test_serialize_json(self):
        config = parse_config(json.dumps(_minimal_config_dict()), "json")
        result = serialize_config(config, "json")
        assert isinstance(result, str)
        parsed_back = json.loads(result)
        assert parsed_back["name"] == "test-pipeline"

    def test_serialize_strips_none(self):
        config = parse_config(json.dumps(_minimal_config_dict()), "json")
        result = serialize_config(config, "json")
        parsed = json.loads(result)
        # system_prompt is None, should be stripped
        assert "system_prompt" not in parsed["agents"][0]

    def test_round_trip_yaml(self):
        original = _full_config_dict()
        raw = yaml.dump(original, sort_keys=False)
        config = parse_config(raw, "yaml")
        serialized = serialize_config(config, "yaml")
        config2 = parse_config(serialized, "yaml")
        assert config == config2

    def test_round_trip_json(self):
        original = _full_config_dict()
        raw = json.dumps(original)
        config = parse_config(raw, "json")
        serialized = serialize_config(config, "json")
        config2 = parse_config(serialized, "json")
        assert config == config2


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------


class TestUnsupportedFormat:
    def test_parse_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            parse_config("{}", "xml")

    def test_serialize_unsupported_format(self):
        config = parse_config(json.dumps(_minimal_config_dict()), "json")
        with pytest.raises(ValueError, match="Unsupported format"):
            serialize_config(config, "xml")
