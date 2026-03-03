# Feature: intent, Property 4: Pipeline agent output chaining
# Feature: intent, Property 5: Pipeline failure halts and reports
# Feature: intent, Property 6: Pipeline accepts any positive agent count
"""Property 4, 5, 6: Pipeline orchestration properties.

Property 4 — For agents [A1..AN], Ai+1's input equals Ai's output.
Property 5 — If agent at step K fails, halt at K, report agent name/step/error, no agents after K execute.
Property 6 — For any positive N, pipeline with N agents is accepted.

**Validates: Requirements 3.1, 3.2, 3.4, 3.5**
"""
from __future__ import annotations

import asyncio

from hypothesis import given, settings, strategies as st

from app.engine.graph_factory import PipelineResult, _FallbackGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracking_agent(name: str):
    """Create a callable agent that appends its name to the input and records what it received."""
    received: list[str] = []

    def agent_fn(input_data: str) -> str:
        received.append(input_data)
        return f"{input_data}->{name}"

    agent_fn.name = name  # type: ignore[attr-defined]
    agent_fn.received = received  # type: ignore[attr-defined]
    return agent_fn


def _make_failing_agent_at(name: str, error_msg: str):
    """Create a callable agent that always raises."""
    received: list[str] = []

    def agent_fn(input_data: str) -> str:
        received.append(input_data)
        raise RuntimeError(error_msg)

    agent_fn.name = name  # type: ignore[attr-defined]
    agent_fn.received = received  # type: ignore[attr-defined]
    return agent_fn


# ---------------------------------------------------------------------------
# Property 4: Pipeline agent output chaining
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=100, deadline=None)
def test_pipeline_agent_output_chaining(n: int):
    """Property 4: For agents [A1..AN], Ai+1's input equals Ai's output.

    **Validates: Requirements 3.1, 3.2**

    Generate N agents (1-10), each transforms input by appending its name.
    Verify that each agent receives the previous agent's output.
    """
    agent_names = [f"agent-{i}" for i in range(n)]
    agents = [_make_tracking_agent(name) for name in agent_names]
    agent_tuples = [(name, agent) for name, agent in zip(agent_names, agents)]

    graph = _FallbackGraph(agents=agent_tuples)
    result: PipelineResult = asyncio.run(graph.execute("start"))

    assert result.status == "COMPLETED"

    # Verify chaining: each agent's input should be the previous agent's output
    expected_input = "start"
    for i, agent in enumerate(agents):
        assert len(agent.received) == 1, f"Agent {i} should have been called exactly once"
        assert agent.received[0] == expected_input, (
            f"Agent {i} received '{agent.received[0]}' but expected '{expected_input}'"
        )
        expected_input = f"{expected_input}->{agent_names[i]}"

    # Final output should be the last agent's output
    assert result.output == expected_input


# ---------------------------------------------------------------------------
# Property 5: Pipeline failure halts and reports
# ---------------------------------------------------------------------------

@given(
    n=st.integers(min_value=2, max_value=10),
    data=st.data(),
)
@settings(max_examples=100, deadline=None)
def test_pipeline_failure_halts_and_reports(n: int, data):
    """Property 5: If agent at step K fails, halt at K, report agent name/step/error, no agents after K execute.

    **Validates: Requirements 3.4**

    Generate N agents (2-10), pick a random failure step K (0 to N-1).
    Verify halt at K with correct error reporting.
    """
    k = data.draw(st.integers(min_value=0, max_value=n - 1))

    agent_names = [f"agent-{i}" for i in range(n)]
    agents = []
    for i, name in enumerate(agent_names):
        if i == k:
            agents.append(_make_failing_agent_at(name, f"error-at-{name}"))
        else:
            agents.append(_make_tracking_agent(name))

    agent_tuples = [(name, agent) for name, agent in zip(agent_names, agents)]

    graph = _FallbackGraph(agents=agent_tuples)
    result: PipelineResult = asyncio.run(graph.execute("start"))

    # Pipeline should have failed
    assert result.status == "FAILED"

    # Error report should contain the failing agent's name, step, and error
    assert result.failed_agent == agent_names[k]
    assert result.failed_step == k
    assert result.error is not None
    assert f"error-at-{agent_names[k]}" in result.error

    # Execution order should contain only agents before the failure
    assert result.execution_order == agent_names[:k]

    # No agents after step K should have been called
    for i in range(k + 1, n):
        assert len(agents[i].received) == 0, (
            f"Agent at step {i} should not have executed after failure at step {k}"
        )


# ---------------------------------------------------------------------------
# Property 6: Pipeline accepts any positive agent count
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=1, max_value=20))
@settings(max_examples=100, deadline=None)
def test_pipeline_accepts_any_positive_agent_count(n: int):
    """Property 6: For any positive N, pipeline with N agents is accepted.

    **Validates: Requirements 3.5**

    Generate N (1-20) agents. Verify pipeline accepts and completes.
    """
    agent_names = [f"agent-{i}" for i in range(n)]
    agents = [_make_tracking_agent(name) for name in agent_names]
    agent_tuples = [(name, agent) for name, agent in zip(agent_names, agents)]

    graph = _FallbackGraph(agents=agent_tuples)
    result: PipelineResult = asyncio.run(graph.execute("input"))

    assert result.status == "COMPLETED"
    assert len(result.execution_order) == n
    assert result.execution_order == agent_names
    assert result.execution_time_ms >= 0
