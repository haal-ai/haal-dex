"""Unit tests for the ReplayEngine service and replay API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.execution import ExecutionStep, SessionLog
from app.models.files import IngestedFile
from app.models.pipeline import AgentConfig, OutputConfig, PipelineConfig, ProviderConfig
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.replay_engine import (
    ReplayEngine,
    ReplaySession,
    ReplayStep,
    TimelineEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_step(step_number: int, *, status: str = "completed", error: str | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_number=step_number,
        agent_id=f"agent_{step_number}",
        agent_name=f"Agent {step_number}",
        status=status,
        timestamp=datetime(2025, 1, 1, 12, step_number, 0, tzinfo=timezone.utc),
        input_data={"key": f"input_{step_number}"},
        prompts_sent=[f"prompt_{step_number}"],
        llm_responses=[f"response_{step_number}"],
        llm_provider="bedrock",
        llm_model="claude-3-sonnet",
        decisions=[f"decision_{step_number}"],
        output_data={"key": f"output_{step_number}"},
        error=error,
    )


def _make_session_log(
    session_id: str = "sess-1",
    num_steps: int = 3,
) -> SessionLog:
    steps = [_make_step(i) for i in range(1, num_steps + 1)]
    return SessionLog(
        session_id=session_id,
        user_id="user-42",
        pipeline_config=PipelineConfig(
            name="test-pipeline",
            agents=[
                AgentConfig(
                    name=f"Agent {i}",
                    model="bedrock/claude-3-sonnet",
                    provider_config=ProviderConfig(provider_type="bedrock", model_id="claude-3-sonnet"),
                    description=f"Agent {i} description",
                )
                for i in range(1, num_steps + 1)
            ],
            output=OutputConfig(template="default", formats=["pdf"]),
        ),
        steps=steps,
        input_files=[],
        output_documents=[],
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=timezone.utc),
    )


def _make_empty_session_log() -> SessionLog:
    """A session log with empty session_id (simulates not found)."""
    return SessionLog(
        session_id="",
        user_id="",
        pipeline_config=PipelineConfig(
            name="",
            agents=[],
            output=OutputConfig(template="", formats=[]),
        ),
        steps=[],
        input_files=[],
        output_documents=[],
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        completed_at=None,
    )


@pytest.fixture
def mock_logger():
    """Return a mock ExecutionLogger."""
    logger = AsyncMock()
    logger.get_session_log = AsyncMock(return_value=_make_session_log())
    return logger


@pytest.fixture
def engine(mock_logger):
    return ReplayEngine(execution_logger=mock_logger)


# ---------------------------------------------------------------------------
# ReplayEngine.load_execution
# ---------------------------------------------------------------------------

class TestLoadExecution:
    @pytest.mark.asyncio
    async def test_returns_replay_session(self, engine: ReplayEngine):
        result = await engine.load_execution("sess-1")
        assert isinstance(result, ReplaySession)
        assert result.session_id == "sess-1"
        assert result.user_id == "user-42"
        assert len(result.steps) == 3
        assert len(result.timeline) == 3

    @pytest.mark.asyncio
    async def test_steps_contain_full_data(self, engine: ReplayEngine):
        result = await engine.load_execution("sess-1")
        step = result.steps[0]
        assert isinstance(step, ReplayStep)
        assert step.step_number == 1
        assert step.agent_id == "agent_1"
        assert step.agent_name == "Agent 1"
        assert step.input_data == {"key": "input_1"}
        assert step.prompts_sent == ["prompt_1"]
        assert step.llm_responses == ["response_1"]
        assert step.llm_provider == "bedrock"
        assert step.llm_model == "claude-3-sonnet"
        assert step.decisions == ["decision_1"]
        assert step.output_data == {"key": "output_1"}
        assert step.error is None

    @pytest.mark.asyncio
    async def test_timeline_entries(self, engine: ReplayEngine):
        result = await engine.load_execution("sess-1")
        entry = result.timeline[0]
        assert isinstance(entry, TimelineEntry)
        assert entry.step_number == 1
        assert entry.agent_id == "agent_1"
        assert entry.agent_name == "Agent 1"
        assert entry.status == "completed"

    @pytest.mark.asyncio
    async def test_session_not_found_raises(self, mock_logger):
        mock_logger.get_session_log = AsyncMock(return_value=_make_empty_session_log())
        engine = ReplayEngine(execution_logger=mock_logger)
        with pytest.raises(ValueError, match="not found"):
            await engine.load_execution("nonexistent")

    @pytest.mark.asyncio
    async def test_steps_are_sequential(self, engine: ReplayEngine):
        result = await engine.load_execution("sess-1")
        step_numbers = [s.step_number for s in result.steps]
        assert step_numbers == [1, 2, 3]


# ---------------------------------------------------------------------------
# ReplayEngine.get_step
# ---------------------------------------------------------------------------

class TestGetStep:
    @pytest.mark.asyncio
    async def test_returns_correct_step(self, engine: ReplayEngine):
        step = await engine.get_step("sess-1", 2)
        assert isinstance(step, ReplayStep)
        assert step.step_number == 2
        assert step.agent_id == "agent_2"

    @pytest.mark.asyncio
    async def test_step_not_found_raises(self, engine: ReplayEngine):
        with pytest.raises(ValueError, match="Step 99 not found"):
            await engine.get_step("sess-1", 99)

    @pytest.mark.asyncio
    async def test_session_not_found_raises(self, mock_logger):
        mock_logger.get_session_log = AsyncMock(return_value=_make_empty_session_log())
        engine = ReplayEngine(execution_logger=mock_logger)
        with pytest.raises(ValueError, match="not found"):
            await engine.get_step("nonexistent", 1)

    @pytest.mark.asyncio
    async def test_step_with_error(self, mock_logger):
        log = _make_session_log(num_steps=1)
        log.steps[0] = _make_step(1, status="failed", error="LLM timeout")
        mock_logger.get_session_log = AsyncMock(return_value=log)
        engine = ReplayEngine(execution_logger=mock_logger)
        step = await engine.get_step("sess-1", 1)
        assert step.status == "failed"
        assert step.error == "LLM timeout"


# ---------------------------------------------------------------------------
# ReplayEngine.get_timeline
# ---------------------------------------------------------------------------

class TestGetTimeline:
    @pytest.mark.asyncio
    async def test_returns_timeline_entries(self, engine: ReplayEngine):
        timeline = await engine.get_timeline("sess-1")
        assert len(timeline) == 3
        assert all(isinstance(e, TimelineEntry) for e in timeline)

    @pytest.mark.asyncio
    async def test_timeline_order(self, engine: ReplayEngine):
        timeline = await engine.get_timeline("sess-1")
        step_numbers = [e.step_number for e in timeline]
        assert step_numbers == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_timeline_fields(self, engine: ReplayEngine):
        timeline = await engine.get_timeline("sess-1")
        entry = timeline[1]
        assert entry.step_number == 2
        assert entry.agent_id == "agent_2"
        assert entry.agent_name == "Agent 2"
        assert entry.status == "completed"
        assert entry.timestamp == datetime(2025, 1, 1, 12, 2, 0, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_session_not_found_raises(self, mock_logger):
        mock_logger.get_session_log = AsyncMock(return_value=_make_empty_session_log())
        engine = ReplayEngine(execution_logger=mock_logger)
        with pytest.raises(ValueError, match="not found"):
            await engine.get_timeline("nonexistent")


# ---------------------------------------------------------------------------
# API endpoint tests (via FastAPI TestClient)
# ---------------------------------------------------------------------------

class TestReplayAPI:
    @pytest.fixture
    def client(self, mock_logger):
        """Create a test client with mocked dependencies."""
        from fastapi.testclient import TestClient

        from app.main import create_app
        from app.api.replay import get_replay_engine
        from app.middleware.auth import get_current_user
        from app.models.auth import UserContext

        app = create_app()

        mock_engine = ReplayEngine(execution_logger=mock_logger)

        async def override_user():
            return UserContext(
                user_id="test-user",
                username="tester",
                roles=["user"],
                token="fake-token",
            )

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_replay_engine] = lambda: mock_engine

        return TestClient(app)

    def test_get_replay_success(self, client):
        resp = client.get("/api/replay/sess-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-1"
        assert len(data["steps"]) == 3
        assert len(data["timeline"]) == 3

    def test_get_replay_step_success(self, client):
        resp = client.get("/api/replay/sess-1/step/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["step_number"] == 1
        assert data["agent_id"] == "agent_1"

    def test_get_replay_not_found(self, client, mock_logger):
        mock_logger.get_session_log = AsyncMock(return_value=_make_empty_session_log())
        resp = client.get("/api/replay/nonexistent")
        assert resp.status_code == 404

    def test_get_replay_step_not_found(self, client):
        resp = client.get("/api/replay/sess-1/step/99")
        assert resp.status_code == 404

    def test_replay_response_structure(self, client):
        resp = client.get("/api/replay/sess-1")
        data = resp.json()
        # Verify top-level keys
        assert "session_id" in data
        assert "user_id" in data
        assert "created_at" in data
        assert "completed_at" in data
        assert "steps" in data
        assert "timeline" in data
        # Verify step structure
        step = data["steps"][0]
        for key in ("step_number", "agent_id", "agent_name", "status",
                     "timestamp", "input_data", "prompts_sent",
                     "llm_responses", "llm_provider", "llm_model",
                     "decisions", "output_data", "error"):
            assert key in step
        # Verify timeline entry structure
        entry = data["timeline"][0]
        for key in ("step_number", "agent_id", "agent_name", "status", "timestamp"):
            assert key in entry
