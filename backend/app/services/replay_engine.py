"""Replay engine for step-by-step replay of past pipeline executions.

Loads completed sessions from the ExecutionLogger and presents each
pipeline step sequentially with the recorded inputs, prompts, responses,
and outputs.  Also provides a timeline summary for navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.execution import ExecutionStep, SessionLog
from app.services.execution_logger import ExecutionLogger


@dataclass
class TimelineEntry:
    """Lightweight summary of a single pipeline step for timeline display."""

    step_number: int
    agent_id: str
    agent_name: str
    status: str
    timestamp: datetime


@dataclass
class ReplayStep:
    """Full data for a single replay step."""

    step_number: int
    agent_id: str
    agent_name: str
    status: str
    timestamp: datetime
    input_data: dict
    prompts_sent: list[str]
    llm_responses: list[str]
    llm_provider: str
    llm_model: str
    decisions: list[str]
    output_data: dict
    error: str | None


@dataclass
class ReplaySession:
    """Complete replay data for a session."""

    session_id: str
    user_id: str
    created_at: datetime
    completed_at: datetime | None
    steps: list[ReplayStep]
    timeline: list[TimelineEntry]


class ReplayEngine:
    """Enables step-by-step replay of past pipeline executions.

    Reads from ExecutionLogger storage and presents steps sequentially
    with all recorded data.
    """

    def __init__(self, execution_logger: ExecutionLogger | None = None) -> None:
        self._logger = execution_logger or ExecutionLogger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_execution(self, session_id: str) -> ReplaySession:
        """Load a past execution from the Execution Logger's stored logs.

        Returns a ``ReplaySession`` containing all steps and a timeline.
        Raises ``ValueError`` if the session does not exist.
        """
        session_log: SessionLog = await self._logger.get_session_log(session_id)
        if not session_log.session_id:
            raise ValueError(f"Session '{session_id}' not found")

        steps = [self._step_to_replay_step(s) for s in session_log.steps]
        timeline = [self._step_to_timeline_entry(s) for s in session_log.steps]

        return ReplaySession(
            session_id=session_log.session_id,
            user_id=session_log.user_id,
            created_at=session_log.created_at,
            completed_at=session_log.completed_at,
            steps=steps,
            timeline=timeline,
        )

    async def get_step(self, session_id: str, step_number: int) -> ReplayStep:
        """Return a single execution step from a past session.

        Raises ``ValueError`` if the session or step does not exist.
        """
        session_log: SessionLog = await self._logger.get_session_log(session_id)
        if not session_log.session_id:
            raise ValueError(f"Session '{session_id}' not found")

        for step in session_log.steps:
            if step.step_number == step_number:
                return self._step_to_replay_step(step)

        raise ValueError(
            f"Step {step_number} not found in session '{session_id}'"
        )

    async def get_timeline(self, session_id: str) -> list[TimelineEntry]:
        """Return a list of step summaries for timeline navigation.

        Raises ``ValueError`` if the session does not exist.
        """
        session_log: SessionLog = await self._logger.get_session_log(session_id)
        if not session_log.session_id:
            raise ValueError(f"Session '{session_id}' not found")

        return [self._step_to_timeline_entry(s) for s in session_log.steps]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _step_to_replay_step(step: ExecutionStep) -> ReplayStep:
        return ReplayStep(
            step_number=step.step_number,
            agent_id=step.agent_id,
            agent_name=step.agent_name,
            status=step.status,
            timestamp=step.timestamp,
            input_data=step.input_data,
            prompts_sent=step.prompts_sent,
            llm_responses=step.llm_responses,
            llm_provider=step.llm_provider,
            llm_model=step.llm_model,
            decisions=step.decisions,
            output_data=step.output_data,
            error=step.error,
        )

    @staticmethod
    def _step_to_timeline_entry(step: ExecutionStep) -> TimelineEntry:
        return TimelineEntry(
            step_number=step.step_number,
            agent_id=step.agent_id,
            agent_name=step.agent_name,
            status=step.status,
            timestamp=step.timestamp,
        )
