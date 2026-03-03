from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentMetrics:
    agent_id: str
    agent_name: str
    input_tokens: int
    output_tokens: int
    llm_call_count: int


@dataclass
class SessionMetrics:
    session_id: str
    agent_metrics: list[AgentMetrics]
