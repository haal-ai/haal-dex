"""Unit tests for GraphFactory — sequential graph building and execution.

Requirements: 3.1, 3.2, 3.4, 3.5, 17.2
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.agent_factory import AgentFactory, AgentSpec
from app.engine.graph_factory import GraphFactory, PipelineResult, _FallbackGraph
from app.models.pipeline import (
    AgentConfig,
    OAuthConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_config() -> ProviderConfig:
    return ProviderConfig(
        provider_type="github_copilot",
        model_id="copilot-gpt-4",
        oauth_config=OAuthConfig(
            client_id="cid",
            client_secret="csec",
            token_url="https://tok",
            scopes=["read"],
        ),
    )


def _agent_config(name: str = "agent-1") -> AgentConfig:
    return AgentConfig(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=_provider_config(),
        description=f"Agent {name}",
        tools=["read"],
    )


def _pipeline_config(
    agent_names: list[str] | None = None,
    timeout: int = 600,
) -> PipelineConfig:
    names = agent_names or ["agent-1"]
    return PipelineConfig(
        name="test-pipeline",
        agents=[_agent_config(n) for n in names],
        output=OutputConfig(template="default", formats=["pdf"]),
        execution_timeout=timeout,
    )


def _make_callable_agent(name: str, transform=None):
    """Create a callable mock agent that transforms input."""
    def agent_fn(input_data):
        if transform:
            return transform(input_data)
        return f"{name}({input_data})"
    agent_fn.name = name
    return agent_fn


def _make_failing_agent(name: str, error_msg: str = "boom"):
    """Create a callable mock agent that raises an exception."""
    def agent_fn(input_data):
        raise RuntimeError(error_msg)
    agent_fn.name = name
    return agent_fn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_model_factory() -> MagicMock:
    factory = MagicMock()
    factory.create_model.return_value = MagicMock(name="mock_model")
    return factory


@pytest.fixture
def agent_factory(mock_model_factory: MagicMock) -> AgentFactory:
    return AgentFactory(model_factory=mock_model_factory)


@pytest.fixture
def graph_factory(agent_factory: AgentFactory) -> GraphFactory:
    return GraphFactory(agent_factory=agent_factory)


# ---------------------------------------------------------------------------
# build_graph — basic construction
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_builds_fallback_graph_when_strands_unavailable(self, graph_factory):
        config = _pipeline_config(["a1", "a2"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config)
        assert isinstance(graph, _FallbackGraph)

    def test_fallback_graph_has_correct_agent_count(self, graph_factory):
        config = _pipeline_config(["a1", "a2", "a3"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config)
        assert len(graph.agents) == 3

    def test_fallback_graph_preserves_agent_order(self, graph_factory):
        config = _pipeline_config(["first", "second", "third"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config)
        node_ids = [nid for nid, _ in graph.agents]
        assert node_ids == ["first", "second", "third"]

    def test_raises_on_empty_agents(self, graph_factory):
        config = PipelineConfig(
            name="empty",
            agents=[],
            output=OutputConfig(template="t", formats=["pdf"]),
        )
        with pytest.raises(ValueError, match="at least one agent"):
            graph_factory.build_graph(config)

    def test_single_agent_pipeline(self, graph_factory):
        config = _pipeline_config(["solo"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config)
        assert len(graph.agents) == 1
        assert graph.agents[0][0] == "solo"

    def test_timeout_passed_to_fallback_graph(self, graph_factory):
        config = _pipeline_config(["a1"], timeout=120)
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config)
        assert graph.timeout == 120

    def test_shared_state_passed_to_fallback_graph(self, graph_factory):
        config = _pipeline_config(["a1"])
        state = {"session_id": "s1"}
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            graph = graph_factory.build_graph(config, shared_state=state)
        assert graph.shared_state == state


# ---------------------------------------------------------------------------
# FallbackGraph — execute (non-streaming)
# ---------------------------------------------------------------------------

class TestFallbackExecute:
    @pytest.mark.asyncio
    async def test_single_agent_returns_output(self):
        agent = _make_callable_agent("a1")
        graph = _FallbackGraph(agents=[("a1", agent)])
        result = await graph.execute("hello")
        assert result.status == "COMPLETED"
        assert result.output == "a1(hello)"
        assert result.execution_order == ["a1"]

    @pytest.mark.asyncio
    async def test_sequential_chaining(self):
        """Agent output flows as input to the next agent (Req 3.2)."""
        a1 = _make_callable_agent("a1")
        a2 = _make_callable_agent("a2")
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2)])
        result = await graph.execute("start")
        assert result.status == "COMPLETED"
        # a2 receives a1's output
        assert result.output == "a2(a1(start))"
        assert result.execution_order == ["a1", "a2"]

    @pytest.mark.asyncio
    async def test_three_agent_chain(self):
        a1 = _make_callable_agent("a1")
        a2 = _make_callable_agent("a2")
        a3 = _make_callable_agent("a3")
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2), ("a3", a3)])
        result = await graph.execute("x")
        assert result.output == "a3(a2(a1(x)))"
        assert result.execution_order == ["a1", "a2", "a3"]

    @pytest.mark.asyncio
    async def test_failure_halts_execution(self):
        """When an agent fails, halt and report (Req 3.4)."""
        a1 = _make_callable_agent("a1")
        a2 = _make_failing_agent("a2", "agent error")
        a3 = _make_callable_agent("a3")
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2), ("a3", a3)])
        result = await graph.execute("input")
        assert result.status == "FAILED"
        assert result.failed_agent == "a2"
        assert result.failed_step == 1
        assert "agent error" in result.error
        # a3 should NOT be in execution_order
        assert "a3" not in result.execution_order
        assert result.execution_order == ["a1"]

    @pytest.mark.asyncio
    async def test_first_agent_failure(self):
        a1 = _make_failing_agent("a1", "first fails")
        a2 = _make_callable_agent("a2")
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2)])
        result = await graph.execute("input")
        assert result.status == "FAILED"
        assert result.failed_agent == "a1"
        assert result.failed_step == 0
        assert result.execution_order == []

    @pytest.mark.asyncio
    async def test_execution_time_is_positive(self):
        a1 = _make_callable_agent("a1")
        graph = _FallbackGraph(agents=[("a1", a1)])
        result = await graph.execute("x")
        assert result.execution_time_ms >= 0


# ---------------------------------------------------------------------------
# FallbackGraph — stream_execute (WebSocket forwarding)
# ---------------------------------------------------------------------------

class TestFallbackStreamExecute:
    @pytest.mark.asyncio
    async def test_stream_sends_events_to_websocket(self):
        """Verify agent_start, agent_complete, pipeline_complete events (Req 17.2)."""
        a1 = _make_callable_agent("a1")
        ws = AsyncMock()
        graph = _FallbackGraph(agents=[("a1", a1)])
        result = await graph.stream_execute(input_data="hello", websocket=ws)

        assert result.status == "COMPLETED"
        calls = ws.send_json.call_args_list
        types = [c.args[0]["type"] for c in calls]
        assert types == ["agent_start", "agent_complete", "pipeline_complete"]

    @pytest.mark.asyncio
    async def test_stream_multi_agent_events(self):
        a1 = _make_callable_agent("a1")
        a2 = _make_callable_agent("a2")
        ws = AsyncMock()
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2)])
        result = await graph.stream_execute(input_data="start", websocket=ws)

        assert result.status == "COMPLETED"
        calls = ws.send_json.call_args_list
        types = [c.args[0]["type"] for c in calls]
        assert types == [
            "agent_start", "agent_complete",
            "agent_start", "agent_complete",
            "pipeline_complete",
        ]

    @pytest.mark.asyncio
    async def test_stream_failure_sends_agent_fail(self):
        a1 = _make_callable_agent("a1")
        a2 = _make_failing_agent("a2", "oops")
        ws = AsyncMock()
        graph = _FallbackGraph(agents=[("a1", a1), ("a2", a2)])
        result = await graph.stream_execute(websocket=ws)

        assert result.status == "FAILED"
        calls = ws.send_json.call_args_list
        types = [c.args[0]["type"] for c in calls]
        assert "agent_fail" in types
        # Verify the fail event has error details
        fail_event = next(c.args[0] for c in calls if c.args[0]["type"] == "agent_fail")
        assert fail_event["agent_id"] == "a2"
        assert "oops" in fail_event["error"]

    @pytest.mark.asyncio
    async def test_stream_without_websocket(self):
        """stream_execute works even without a websocket (no events sent)."""
        a1 = _make_callable_agent("a1")
        graph = _FallbackGraph(agents=[("a1", a1)])
        result = await graph.stream_execute(websocket=None)
        assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_stream_agent_ids_match(self):
        a1 = _make_callable_agent("alpha")
        a2 = _make_callable_agent("beta")
        ws = AsyncMock()
        graph = _FallbackGraph(agents=[("alpha", a1), ("beta", a2)])
        await graph.stream_execute(websocket=ws)

        calls = ws.send_json.call_args_list
        start_events = [c.args[0] for c in calls if c.args[0]["type"] == "agent_start"]
        assert start_events[0]["agent_id"] == "alpha"
        assert start_events[1]["agent_id"] == "beta"


# ---------------------------------------------------------------------------
# FallbackGraph — stream_events (async generator)
# ---------------------------------------------------------------------------

class TestFallbackStreamEvents:
    @pytest.mark.asyncio
    async def test_yields_correct_event_sequence(self):
        a1 = _make_callable_agent("a1")
        graph = _FallbackGraph(agents=[("a1", a1)])
        events = [e async for e in graph.stream_events("input")]
        types = [e["type"] for e in events]
        assert types == ["agent_start", "agent_complete", "pipeline_complete"]

    @pytest.mark.asyncio
    async def test_yields_fail_event_on_error(self):
        a1 = _make_failing_agent("a1", "fail!")
        graph = _FallbackGraph(agents=[("a1", a1)])
        events = [e async for e in graph.stream_events("input")]
        types = [e["type"] for e in events]
        assert types == ["agent_start", "agent_fail"]
        assert "fail!" in events[1]["error"]


# ---------------------------------------------------------------------------
# GraphFactory — execute (high-level)
# ---------------------------------------------------------------------------

class TestGraphFactoryExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_completed(self, graph_factory):
        config = _pipeline_config(["a1"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            result = await graph_factory.execute(config, input_data="hello")
        assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_execute_chains_agents(self, graph_factory):
        config = _pipeline_config(["a1", "a2"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            result = await graph_factory.execute(config, input_data="x")
        # AgentSpec fallback is not callable, so passthrough
        assert result.status == "COMPLETED"
        assert result.execution_order == ["a1", "a2"]


# ---------------------------------------------------------------------------
# GraphFactory — stream_execute (high-level)
# ---------------------------------------------------------------------------

class TestGraphFactoryStreamExecute:
    @pytest.mark.asyncio
    async def test_stream_execute_sends_events(self, graph_factory):
        config = _pipeline_config(["a1"])
        ws = AsyncMock()
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            result = await graph_factory.stream_execute(
                config, input_data="hello", websocket=ws,
            )
        assert result.status == "COMPLETED"
        assert ws.send_json.called

    @pytest.mark.asyncio
    async def test_stream_execute_without_websocket(self, graph_factory):
        config = _pipeline_config(["a1"])
        with patch("app.engine.graph_factory._GRAPH_BUILDER_AVAILABLE", False):
            result = await graph_factory.stream_execute(config, input_data="hello")
        assert result.status == "COMPLETED"


# ---------------------------------------------------------------------------
# PipelineResult dataclass
# ---------------------------------------------------------------------------

class TestPipelineResult:
    def test_default_values(self):
        r = PipelineResult(status="COMPLETED")
        assert r.output is None
        assert r.execution_order == []
        assert r.execution_time_ms == 0.0
        assert r.error is None
        assert r.failed_agent is None
        assert r.failed_step is None

    def test_failed_result(self):
        r = PipelineResult(
            status="FAILED",
            error="timeout",
            failed_agent="a2",
            failed_step=1,
        )
        assert r.status == "FAILED"
        assert r.failed_agent == "a2"
        assert r.failed_step == 1


# ---------------------------------------------------------------------------
# Agent count flexibility (Req 3.5)
# ---------------------------------------------------------------------------

class TestAgentCountFlexibility:
    @pytest.mark.asyncio
    async def test_single_agent(self):
        a1 = _make_callable_agent("a1")
        graph = _FallbackGraph(agents=[("a1", a1)])
        result = await graph.execute("x")
        assert result.status == "COMPLETED"
        assert len(result.execution_order) == 1

    @pytest.mark.asyncio
    async def test_five_agents(self):
        agents = [(_make_callable_agent(f"a{i}"), f"a{i}") for i in range(5)]
        agent_tuples = [(name, agent) for agent, name in agents]
        graph = _FallbackGraph(agents=agent_tuples)
        result = await graph.execute("x")
        assert result.status == "COMPLETED"
        assert len(result.execution_order) == 5

    @pytest.mark.asyncio
    async def test_ten_agents(self):
        agents = [(f"a{i}", _make_callable_agent(f"a{i}")) for i in range(10)]
        graph = _FallbackGraph(agents=agents)
        result = await graph.execute("x")
        assert result.status == "COMPLETED"
        assert len(result.execution_order) == 10
