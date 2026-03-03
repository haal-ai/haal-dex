"""GraphFactory: translates PipelineConfig into a Strands Graph for execution.

Builds a sequential topology from PipelineConfig using GraphBuilder (when
available) or a lightweight fallback that chains agents sequentially.

Supports both synchronous ``execute()`` and streaming ``stream_execute()``
which forwards events to a WebSocket connection.

Requirements: 3.1, 3.2, 3.4, 3.5, 17.2
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.engine.agent_factory import AgentFactory
from app.models.pipeline import PipelineConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try importing Strands SDK GraphBuilder; fall back gracefully.
# ---------------------------------------------------------------------------
try:
    from strands_agents.graph import GraphBuilder

    _GRAPH_BUILDER_AVAILABLE = True
except ImportError:
    GraphBuilder = None  # type: ignore[assignment,misc]
    _GRAPH_BUILDER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Outcome of a pipeline execution."""

    status: str  # "COMPLETED" | "FAILED"
    output: Any = None
    execution_order: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error: str | None = None
    failed_agent: str | None = None
    failed_step: int | None = None


# ---------------------------------------------------------------------------
# GraphFactory
# ---------------------------------------------------------------------------

class GraphFactory:
    """Translates PipelineConfig into a Strands Graph for execution."""

    def __init__(self, agent_factory: AgentFactory) -> None:
        self.agent_factory = agent_factory

    # ------------------------------------------------------------------
    # Graph building
    # ------------------------------------------------------------------

    def build_graph(self, config: PipelineConfig, shared_state: dict | None = None):
        """Build a Strands Graph from PipelineConfig with sequential topology.

        When the Strands SDK ``GraphBuilder`` is available the real graph is
        returned.  Otherwise a ``_FallbackGraph`` is returned that mimics the
        same execution semantics.
        """
        if not config.agents:
            raise ValueError("PipelineConfig must contain at least one agent")

        if _GRAPH_BUILDER_AVAILABLE:
            return self._build_strands_graph(config, shared_state)
        return self._build_fallback_graph(config, shared_state)

    # ------------------------------------------------------------------
    # Strands SDK path
    # ------------------------------------------------------------------

    def _build_strands_graph(self, config: PipelineConfig, shared_state: dict | None):
        builder = GraphBuilder()

        for i, agent_config in enumerate(config.agents):
            agent = self.agent_factory.create_agent(agent_config)
            node_id = agent_config.name
            builder.add_node(agent, node_id)

            if i > 0:
                prev_node_id = config.agents[i - 1].name
                builder.add_edge(prev_node_id, node_id)

        builder.set_entry_point(config.agents[0].name)
        builder.set_execution_timeout(config.execution_timeout or 600)
        return builder.build()

    # ------------------------------------------------------------------
    # Fallback path (no Strands SDK)
    # ------------------------------------------------------------------

    def _build_fallback_graph(self, config: PipelineConfig, shared_state: dict | None):
        agents = []
        for agent_config in config.agents:
            agent = self.agent_factory.create_agent(agent_config)
            agents.append((agent_config.name, agent))
        return _FallbackGraph(
            agents=agents,
            timeout=config.execution_timeout or 600,
            shared_state=shared_state or {},
        )

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    async def execute(
        self,
        config: PipelineConfig,
        input_data: str = "",
        shared_state: dict | None = None,
    ) -> PipelineResult:
        """Execute the pipeline and return the final result."""
        graph = self.build_graph(config, shared_state)
        invocation_state = shared_state or {}

        if _GRAPH_BUILDER_AVAILABLE:
            result = graph(input_data, invocation_state=invocation_state)
            return self._strands_result_to_pipeline_result(result)

        # Fallback execution
        return await graph.execute(input_data)

    async def stream_execute(
        self,
        config: PipelineConfig,
        input_data: str = "",
        shared_state: dict | None = None,
        websocket: Any | None = None,
    ) -> PipelineResult:
        """Execute with streaming events forwarded to WebSocket."""
        graph = self.build_graph(config, shared_state)
        invocation_state = shared_state or {}

        if _GRAPH_BUILDER_AVAILABLE:
            return await self._stream_strands(graph, input_data, invocation_state, websocket)

        # Fallback streaming
        return await graph.stream_execute(input_data=input_data, websocket=websocket)

    # ------------------------------------------------------------------
    # Strands streaming
    # ------------------------------------------------------------------

    async def _stream_strands(self, graph, input_data, invocation_state, websocket):
        async for event in graph.stream_async(input_data, invocation_state=invocation_state):
            event_type = event.get("type", "")
            if websocket is not None:
                if event_type == "multiagent_node_start":
                    await websocket.send_json({
                        "type": "agent_start",
                        "agent_id": event.get("node_id"),
                    })
                elif event_type == "multiagent_node_stream":
                    await websocket.send_json({
                        "type": "llm_token",
                        "agent_id": event.get("node_id"),
                        "content": event.get("delta", ""),
                    })
                elif event_type == "multiagent_node_stop":
                    await websocket.send_json({
                        "type": "agent_complete",
                        "agent_id": event.get("node_id"),
                    })
                elif event_type == "multiagent_result":
                    return self._strands_result_to_pipeline_result(event.get("result"))

        # If we exit the loop without a result event, treat as completed
        return PipelineResult(status="COMPLETED")

    @staticmethod
    def _strands_result_to_pipeline_result(result) -> PipelineResult:
        if result is None:
            return PipelineResult(status="COMPLETED")
        status = getattr(result, "status", "COMPLETED")
        return PipelineResult(
            status=str(status),
            output=getattr(result, "output", None),
            execution_order=getattr(result, "execution_order", []),
            execution_time_ms=getattr(result, "execution_time", 0.0),
        )


# ---------------------------------------------------------------------------
# Fallback graph implementation
# ---------------------------------------------------------------------------

class _FallbackGraph:
    """Lightweight sequential graph used when Strands SDK is not installed.

    Chains agents sequentially: each agent's output becomes the next agent's
    input.  Yields events compatible with the WebSocket streaming protocol.
    Halts on failure and reports the failing agent.
    """

    def __init__(
        self,
        agents: list[tuple[str, Any]],
        timeout: int = 600,
        shared_state: dict | None = None,
    ) -> None:
        self.agents = agents  # list of (node_id, agent_instance)
        self.timeout = timeout
        self.shared_state = shared_state or {}

    # ------------------------------------------------------------------
    # Non-streaming execution
    # ------------------------------------------------------------------

    async def execute(self, input_data: str = "") -> PipelineResult:
        """Run all agents sequentially, chaining outputs."""
        start = time.monotonic()
        current_input = input_data
        execution_order: list[str] = []

        for step, (node_id, agent) in enumerate(self.agents):
            try:
                output = self._invoke_agent(agent, current_input)
                current_input = output
                execution_order.append(node_id)
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                return PipelineResult(
                    status="FAILED",
                    execution_order=execution_order,
                    execution_time_ms=elapsed,
                    error=str(exc),
                    failed_agent=node_id,
                    failed_step=step,
                )

        elapsed = (time.monotonic() - start) * 1000
        return PipelineResult(
            status="COMPLETED",
            output=current_input,
            execution_order=execution_order,
            execution_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # Streaming execution
    # ------------------------------------------------------------------

    async def stream_execute(self, input_data: str = "", websocket: Any | None = None) -> PipelineResult:
        """Run agents sequentially, yielding events and forwarding to websocket."""
        start = time.monotonic()
        current_input = input_data
        execution_order: list[str] = []

        for step, (node_id, agent) in enumerate(self.agents):
            # Emit agent_start
            event_start = {
                "type": "agent_start",
                "agent_id": node_id,
                "step": step,
            }
            if websocket is not None:
                await websocket.send_json(event_start)

            try:
                output = self._invoke_agent(agent, current_input)
                current_input = output
                execution_order.append(node_id)
            except Exception as exc:
                # Emit failure event
                elapsed = (time.monotonic() - start) * 1000
                event_fail = {
                    "type": "agent_fail",
                    "agent_id": node_id,
                    "step": step,
                    "error": str(exc),
                }
                if websocket is not None:
                    await websocket.send_json(event_fail)
                return PipelineResult(
                    status="FAILED",
                    execution_order=execution_order,
                    execution_time_ms=elapsed,
                    error=str(exc),
                    failed_agent=node_id,
                    failed_step=step,
                )

            # Emit agent_complete
            event_complete = {
                "type": "agent_complete",
                "agent_id": node_id,
                "step": step,
            }
            if websocket is not None:
                await websocket.send_json(event_complete)

        elapsed = (time.monotonic() - start) * 1000
        # Emit pipeline_complete
        event_done = {
            "type": "pipeline_complete",
            "status": "COMPLETED",
            "execution_order": execution_order,
            "execution_time_ms": elapsed,
        }
        if websocket is not None:
            await websocket.send_json(event_done)

        return PipelineResult(
            status="COMPLETED",
            output=current_input,
            execution_order=execution_order,
            execution_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # Async generator for events (used by tests / consumers)
    # ------------------------------------------------------------------

    async def stream_events(self, input_data: str = "") -> AsyncIterator[dict]:
        """Yield events as dicts for each agent execution step."""
        start = time.monotonic()
        current_input = input_data
        execution_order: list[str] = []

        for step, (node_id, agent) in enumerate(self.agents):
            yield {"type": "agent_start", "agent_id": node_id, "step": step}

            try:
                output = self._invoke_agent(agent, current_input)
                current_input = output
                execution_order.append(node_id)
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                yield {
                    "type": "agent_fail",
                    "agent_id": node_id,
                    "step": step,
                    "error": str(exc),
                }
                return

            yield {"type": "agent_complete", "agent_id": node_id, "step": step}

        elapsed = (time.monotonic() - start) * 1000
        yield {
            "type": "pipeline_complete",
            "status": "COMPLETED",
            "execution_order": execution_order,
            "execution_time_ms": elapsed,
        }

    # ------------------------------------------------------------------
    # Agent invocation
    # ------------------------------------------------------------------

    @staticmethod
    def _invoke_agent(agent: Any, input_data: str) -> str:
        """Invoke an agent (or AgentSpec fallback) with the given input.

        For a real strands.Agent this would call ``agent(input_data)``.
        For the AgentSpec fallback we call it if callable, otherwise
        return the input unchanged (passthrough).
        """
        if callable(agent):
            result = agent(input_data)
            return str(result) if result is not None else input_data
        return input_data
