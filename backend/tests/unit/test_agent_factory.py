"""Unit tests for AgentFactory — agent creation, tool selection, and denied tool logging.

Requirements: 3.1, 4.1, 5.2, 6.5, 6.6
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.engine.agent_factory import AgentFactory, AgentSpec
from app.engine.tools import ALL_TOOLS
from app.models.pipeline import AgentConfig, OAuthConfig, ProviderConfig


@pytest.fixture
def mock_model_factory() -> MagicMock:
    factory = MagicMock()
    factory.create_model.return_value = MagicMock(name="mock_model")
    return factory


@pytest.fixture
def agent_factory(mock_model_factory: MagicMock) -> AgentFactory:
    return AgentFactory(model_factory=mock_model_factory)


def _make_agent_config(
    name: str = "test-agent",
    tools: list[str] | None = None,
    faiss_indexes: list[int] | None = None,
    system_prompt: str | None = None,
    description: str = "A test agent",
) -> AgentConfig:
    return AgentConfig(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-gpt-4",
            oauth_config=OAuthConfig(
                client_id="cid",
                client_secret="csec",
                token_url="https://tok",
                scopes=["read"],
            ),
        ),
        description=description,
        system_prompt=system_prompt,
        tools=tools or [],
        faiss_indexes=faiss_indexes or [],
    )


def _create_agent_via_fallback(agent_factory: AgentFactory, config: AgentConfig) -> AgentSpec:
    """Create agent using the AgentSpec fallback to inspect tools directly."""
    with patch("app.engine.agent_factory._STRANDS_AGENT_AVAILABLE", False):
        agent = agent_factory.create_agent(config)
    assert isinstance(agent, AgentSpec)
    return agent


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


class TestModelResolution:
    def test_delegates_to_model_factory(
        self, agent_factory: AgentFactory, mock_model_factory: MagicMock
    ):
        config = _make_agent_config()
        _create_agent_via_fallback(agent_factory, config)
        mock_model_factory.create_model.assert_called_once_with(config.provider_config)

    def test_agent_receives_model_from_factory(
        self, agent_factory: AgentFactory, mock_model_factory: MagicMock
    ):
        expected_model = MagicMock(name="expected_model")
        mock_model_factory.create_model.return_value = expected_model

        config = _make_agent_config()
        agent = _create_agent_via_fallback(agent_factory, config)
        assert agent.model is expected_model


# ---------------------------------------------------------------------------
# Tool selection
# ---------------------------------------------------------------------------


class TestToolSelection:
    def test_selects_permitted_tools(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["read", "write"])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert ALL_TOOLS["read"] in agent.tools
        assert ALL_TOOLS["write"] in agent.tools
        assert len(agent.tools) == 2

    def test_no_tools_when_none_configured(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=[])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert agent.tools == []

    def test_all_valid_tools_can_be_selected(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["read", "write", "python_repl", "shell"])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert len(agent.tools) == 4
        for tool_name in ["read", "write", "python_repl", "shell"]:
            assert ALL_TOOLS[tool_name] in agent.tools

    def test_excludes_unknown_tools(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["read", "nonexistent_tool"])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert len(agent.tools) == 1
        assert ALL_TOOLS["read"] in agent.tools


# ---------------------------------------------------------------------------
# FAISS tool auto-inclusion
# ---------------------------------------------------------------------------


class TestFaissToolInclusion:
    def test_adds_query_faiss_when_faiss_indexes_present(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["read"], faiss_indexes=[0, 1])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert ALL_TOOLS["query_faiss"] in agent.tools
        assert ALL_TOOLS["read"] in agent.tools
        assert len(agent.tools) == 2

    def test_no_query_faiss_when_no_faiss_indexes(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["read"], faiss_indexes=[])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert ALL_TOOLS["query_faiss"] not in agent.tools
        assert len(agent.tools) == 1

    def test_no_duplicate_query_faiss_if_already_in_tools(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=["query_faiss"], faiss_indexes=[0])
        agent = _create_agent_via_fallback(agent_factory, config)
        faiss_count = sum(1 for t in agent.tools if t is ALL_TOOLS["query_faiss"])
        assert faiss_count == 1

    def test_query_faiss_added_even_with_no_other_tools(self, agent_factory: AgentFactory):
        config = _make_agent_config(tools=[], faiss_indexes=[2])
        agent = _create_agent_via_fallback(agent_factory, config)
        assert ALL_TOOLS["query_faiss"] in agent.tools
        assert len(agent.tools) == 1


# ---------------------------------------------------------------------------
# Denied tool logging
# ---------------------------------------------------------------------------


class TestDeniedToolLogging:
    def test_logs_warning_for_unknown_tool(
        self, agent_factory: AgentFactory, caplog: pytest.LogCaptureFixture
    ):
        config = _make_agent_config(name="my-agent", tools=["read", "bad_tool"])
        with caplog.at_level(logging.WARNING, logger="app.engine.agent_factory"):
            _create_agent_via_fallback(agent_factory, config)
        assert any("bad_tool" in record.message for record in caplog.records)
        assert any("my-agent" in record.message for record in caplog.records)

    def test_no_warning_for_valid_tools(
        self, agent_factory: AgentFactory, caplog: pytest.LogCaptureFixture
    ):
        config = _make_agent_config(tools=["read", "write"])
        with caplog.at_level(logging.WARNING, logger="app.engine.agent_factory"):
            _create_agent_via_fallback(agent_factory, config)
        assert len(caplog.records) == 0

    def test_logs_multiple_denied_tools(
        self, agent_factory: AgentFactory, caplog: pytest.LogCaptureFixture
    ):
        config = _make_agent_config(tools=["foo", "bar", "read"])
        with caplog.at_level(logging.WARNING, logger="app.engine.agent_factory"):
            _create_agent_via_fallback(agent_factory, config)
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) == 2
        assert any("foo" in msg for msg in warning_messages)
        assert any("bar" in msg for msg in warning_messages)


# ---------------------------------------------------------------------------
# System prompt resolution
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_uses_system_prompt_when_provided(self, agent_factory: AgentFactory):
        config = _make_agent_config(
            system_prompt="Custom prompt", description="Fallback description"
        )
        agent = _create_agent_via_fallback(agent_factory, config)
        assert agent.system_prompt == "Custom prompt"

    def test_falls_back_to_description(self, agent_factory: AgentFactory):
        config = _make_agent_config(system_prompt=None, description="Agent description")
        agent = _create_agent_via_fallback(agent_factory, config)
        assert agent.system_prompt == "Agent description"


# ---------------------------------------------------------------------------
# Agent name
# ---------------------------------------------------------------------------


class TestAgentName:
    def test_agent_name_matches_config(self, agent_factory: AgentFactory):
        config = _make_agent_config(name="content-generator")
        agent = _create_agent_via_fallback(agent_factory, config)
        assert agent.name == "content-generator"


# ---------------------------------------------------------------------------
# Strands Agent integration (when SDK is available)
# ---------------------------------------------------------------------------


class TestStrandsAgentIntegration:
    def test_creates_strands_agent_when_available(
        self, agent_factory: AgentFactory
    ):
        """Verify that a real strands.Agent is created when the SDK is available."""
        config = _make_agent_config(tools=["read"], system_prompt="Do stuff")
        with patch("app.engine.agent_factory._STRANDS_AGENT_AVAILABLE", True):
            mock_agent_cls = MagicMock()
            mock_agent_instance = MagicMock()
            mock_agent_cls.return_value = mock_agent_instance
            with patch("app.engine.agent_factory.Agent", mock_agent_cls):
                agent = agent_factory.create_agent(config)

        mock_agent_cls.assert_called_once()
        call_kwargs = mock_agent_cls.call_args
        assert call_kwargs.kwargs["system_prompt"] == "Do stuff"
        assert call_kwargs.kwargs["name"] == "test-agent"
        assert ALL_TOOLS["read"] in call_kwargs.kwargs["tools"]
        assert agent is mock_agent_instance


# ---------------------------------------------------------------------------
# Fallback AgentSpec (when strands not installed)
# ---------------------------------------------------------------------------


class TestAgentSpecFallback:
    def test_returns_agent_spec_when_strands_unavailable(
        self, agent_factory: AgentFactory
    ):
        config = _make_agent_config(tools=["read"], system_prompt="Do stuff")
        agent = _create_agent_via_fallback(agent_factory, config)
        assert isinstance(agent, AgentSpec)
        assert agent.name == config.name
        assert agent.system_prompt == "Do stuff"
        assert ALL_TOOLS["read"] in agent.tools
