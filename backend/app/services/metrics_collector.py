"""MetricsCollector — records token usage and LLM call counts per agent per session."""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from app.models.metrics import AgentMetrics, SessionMetrics


class MetricsCollector:
    """In-memory metrics store keyed by session_id.

    Each session tracks per-agent counters for input tokens, output tokens,
    and LLM call count.
    """

    def __init__(self) -> None:
        # {session_id: {agent_id: {"input_tokens": int, "output_tokens": int, "llm_call_count": int}}}
        self._data: dict[str, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "llm_call_count": 0})
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        session_id: str,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record a single LLM call for *agent_id* within *session_id*."""
        bucket = self._data[session_id][agent_id]
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["llm_call_count"] += 1

    def record_from_node_result(self, session_id: str, node_result: dict) -> None:
        """Extract metrics from a Strands node result dict and record them.

        Expected *node_result* shape::

            {
                "agent_id": "...",
                "usage": {
                    "input_tokens": int,
                    "output_tokens": int,
                },
            }
        """
        agent_id: str = node_result.get("agent_id", "unknown")
        usage: dict = node_result.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        self.record(session_id, agent_id, input_tokens, output_tokens)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_session_metrics(self, session_id: str) -> SessionMetrics:
        """Return a :class:`SessionMetrics` with per-agent breakdown."""
        agents = self._data.get(session_id, {})
        agent_metrics = [
            AgentMetrics(
                agent_id=agent_id,
                agent_name=agent_id,
                input_tokens=counters["input_tokens"],
                output_tokens=counters["output_tokens"],
                llm_call_count=counters["llm_call_count"],
            )
            for agent_id, counters in agents.items()
        ]
        return SessionMetrics(session_id=session_id, agent_metrics=agent_metrics)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self, session_id: str) -> str:
        """Return a CSV string with columns:

        ``session_id, agent_id, input_tokens, output_tokens, llm_call_count``
        """
        metrics = self.get_session_metrics(session_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["session_id", "agent_id", "input_tokens", "output_tokens", "llm_call_count"])
        for am in metrics.agent_metrics:
            writer.writerow([metrics.session_id, am.agent_id, am.input_tokens, am.output_tokens, am.llm_call_count])
        return buf.getvalue()
