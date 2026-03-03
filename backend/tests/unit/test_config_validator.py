"""Unit tests for PipelineConfig validation.

Validates: Requirements 14.3, 14.4
"""

from __future__ import annotations

import pytest

from app.models.pipeline import (
    AgentConfig,
    OAuthConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.services.config_validator import validate_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bedrock_provider(**overrides) -> ProviderConfig:
    defaults = dict(
        provider_type="bedrock",
        model_id="anthropic.claude-3-sonnet",
        region="us-east-1",
    )
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def _agent(name: str = "agent1", **overrides) -> AgentConfig:
    defaults = dict(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=_bedrock_provider(),
        description="A test agent",
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _valid_config(**overrides) -> PipelineConfig:
    defaults = dict(
        name="test-pipeline",
        agents=[_agent()],
        output=OutputConfig(template="default", formats=["xml"]),
    )
    defaults.update(overrides)
    return PipelineConfig(**defaults)


# ---------------------------------------------------------------------------
# Tests — valid config
# ---------------------------------------------------------------------------


class TestValidConfig:
    def test_minimal_valid_config(self):
        errors = validate_config(_valid_config())
        assert errors == []

    def test_multiple_agents(self):
        cfg = _valid_config(agents=[_agent("a1"), _agent("a2")])
        assert validate_config(cfg) == []

    def test_all_valid_tools(self):
        agent = _agent(tools=["read", "write", "python_repl", "shell", "query_faiss"])
        assert validate_config(_valid_config(agents=[agent])) == []

    def test_all_valid_output_formats(self):
        cfg = _valid_config(
            output=OutputConfig(template="t", formats=["xml", "pdf", "docx", "md", "html"])
        )
        assert validate_config(cfg) == []

    def test_valid_faiss_indexes(self):
        agent = _agent(faiss_indexes=[0, 1, 2, 3])
        assert validate_config(_valid_config(agents=[agent])) == []


# ---------------------------------------------------------------------------
# Tests — agent validation
# ---------------------------------------------------------------------------


class TestAgentValidation:
    def test_no_agents(self):
        cfg = _valid_config(agents=[])
        errors = validate_config(cfg)
        assert any("at least one agent" in e for e in errors)

    def test_empty_agent_name(self):
        agent = _agent(name="")
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("name must be non-empty" in e for e in errors)

    def test_whitespace_agent_name(self):
        agent = _agent(name="   ")
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("name must be non-empty" in e for e in errors)

    def test_duplicate_agent_names(self):
        cfg = _valid_config(agents=[_agent("dup"), _agent("dup")])
        errors = validate_config(cfg)
        assert any("duplicate agent name 'dup'" in e for e in errors)

    def test_invalid_provider_type(self):
        provider = _bedrock_provider(provider_type="unknown")
        agent = _agent(provider_config=provider)
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("invalid provider_type 'unknown'" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — provider-specific requirements
# ---------------------------------------------------------------------------


class TestProviderRequirements:
    def test_github_copilot_requires_oauth(self):
        provider = ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-model",
            oauth_config=None,
        )
        agent = _agent(provider_config=provider)
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("requires oauth_config" in e for e in errors)

    def test_github_copilot_with_oauth_is_valid(self):
        oauth = OAuthConfig(
            client_id="id", client_secret="secret",
            token_url="https://example.com/token", scopes=["read"],
        )
        provider = ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-model",
            oauth_config=oauth,
        )
        agent = _agent(provider_config=provider)
        errors = validate_config(_valid_config(agents=[agent]))
        assert errors == []

    def test_bedrock_requires_region(self):
        provider = ProviderConfig(
            provider_type="bedrock",
            model_id="anthropic.claude-3-sonnet",
            region=None,
        )
        agent = _agent(provider_config=provider)
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("requires region" in e for e in errors)

    def test_bedrock_with_region_is_valid(self):
        errors = validate_config(_valid_config())
        assert errors == []


# ---------------------------------------------------------------------------
# Tests — tool and FAISS validation
# ---------------------------------------------------------------------------


class TestToolAndFaissValidation:
    def test_invalid_tool_name(self):
        agent = _agent(tools=["read", "invalid_tool"])
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("invalid tool name 'invalid_tool'" in e for e in errors)

    def test_faiss_index_out_of_range_negative(self):
        agent = _agent(faiss_indexes=[-1])
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("FAISS index -1 out of range" in e for e in errors)

    def test_faiss_index_out_of_range_high(self):
        agent = _agent(faiss_indexes=[4])
        errors = validate_config(_valid_config(agents=[agent]))
        assert any("FAISS index 4 out of range" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — output validation
# ---------------------------------------------------------------------------


class TestOutputValidation:
    def test_empty_formats(self):
        cfg = _valid_config(output=OutputConfig(template="t", formats=[]))
        errors = validate_config(cfg)
        assert any("at least one format" in e for e in errors)

    def test_invalid_output_format(self):
        cfg = _valid_config(output=OutputConfig(template="t", formats=["csv"]))
        errors = validate_config(cfg)
        assert any("invalid format 'csv'" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — multiple errors
# ---------------------------------------------------------------------------


class TestMultipleErrors:
    def test_reports_all_errors(self):
        """Multiple issues should all be reported, not just the first."""
        provider = ProviderConfig(
            provider_type="unknown_provider",
            model_id="m",
            region=None,
        )
        agent = _agent(
            name="",
            provider_config=provider,
            tools=["bad_tool"],
            faiss_indexes=[99],
        )
        cfg = PipelineConfig(
            name="bad",
            agents=[agent],
            output=OutputConfig(template="t", formats=["nope"]),
        )
        errors = validate_config(cfg)
        # Should have errors for: empty name, invalid provider, invalid tool,
        # FAISS out of range, invalid output format
        assert len(errors) >= 4
