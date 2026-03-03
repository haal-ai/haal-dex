"""Unit tests for pipeline execution REST and WebSocket endpoints.

Requirements: 3.1, 3.2, 13.2, 17.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.pipeline import (
    _sessions,
    _session_configs,
    _session_files,
    _get_orchestrator,
    get_sessions,
    router,
    store_session_config,
    store_session_files,
)
from app.engine.graph_factory import PipelineResult
from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.models.session import Session
from app.pipeline_orchestrator import PipelineOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user() -> UserContext:
    return UserContext(
        user_id="user-1",
        username="testuser",
        roles=["user"],
        token="fake-token",
    )


def _provider_config() -> ProviderConfig:
    return ProviderConfig(
        provider_type="bedrock",
        model_id="claude-3-sonnet",
    )


def _agent_config(name: str = "agent-1") -> AgentConfig:
    return AgentConfig(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=_provider_config(),
        description=f"Agent {name}",
    )


def _pipeline_config(agent_names: list[str] | None = None) -> PipelineConfig:
    names = agent_names or ["agent-1"]
    return PipelineConfig(
        name="test-pipeline",
        agents=[_agent_config(n) for n in names],
        output=OutputConfig(template="default", formats=["pdf"]),
    )


def _pipeline_config_dict(agent_names: list[str] | None = None) -> dict:
    """Return a JSON-serializable dict matching PipelineConfig structure."""
    names = agent_names or ["agent-1"]
    return {
        "name": "test-pipeline",
        "agents": [
            {
                "name": n,
                "model": "bedrock/claude-3-sonnet",
                "provider_config": {
                    "provider_type": "bedrock",
                    "model_id": "claude-3-sonnet",
                },
                "description": f"Agent {n}",
            }
            for n in names
        ],
        "output": {"template": "default", "formats": ["pdf"]},
    }


def _create_session(user_id: str, pipeline_config_name: str) -> Session:
    """Helper to create and store a session for WebSocket tests."""
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        pipeline_config_id=pipeline_config_name,
        status="pending",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        input_files=[],
        output_documents=[],
    )
    _sessions[session.id] = session
    return session


# ---------------------------------------------------------------------------
# App fixture with dependency overrides
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session stores before each test."""
    _sessions.clear()
    _session_configs.clear()
    _session_files.clear()
    yield
    _sessions.clear()
    _session_configs.clear()
    _session_files.clear()


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock PipelineOrchestrator that returns successful results."""
    orch = MagicMock(spec=PipelineOrchestrator)

    # create_session returns a real Session
    def _create(user_id, config):
        s = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            pipeline_config_id=config.name,
            status="pending",
            created_at=datetime.now(timezone.utc),
            completed_at=None,
            input_files=[],
            output_documents=[],
        )
        return s

    orch.create_session = MagicMock(side_effect=_create)

    orch.run_pipeline = AsyncMock(
        return_value=(
            PipelineResult(
                status="COMPLETED",
                output="result-output",
                execution_order=["agent-1"],
                execution_time_ms=42.0,
            ),
            None,  # no rendered doc
        )
    )
    orch.stream_pipeline = AsyncMock(
        return_value=(
            PipelineResult(
                status="COMPLETED",
                output="streamed-output",
                execution_order=["agent-1"],
                execution_time_ms=55.0,
            ),
            None,
        )
    )
    return orch


@pytest.fixture
def app(mock_orchestrator: MagicMock) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router)

    # Override dependencies
    test_app.dependency_overrides[get_current_user] = lambda: _mock_user()
    test_app.dependency_overrides[_get_orchestrator] = lambda: mock_orchestrator

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Session management tests
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_store_session_config(self):
        store_session_config("s1", _pipeline_config())
        assert "s1" in _session_configs

    def test_get_sessions_returns_store(self):
        sessions = get_sessions()
        assert sessions is _sessions

    def test_store_session_files(self):
        store_session_files("s1", [])
        assert "s1" in _session_files


# ---------------------------------------------------------------------------
# POST /api/pipeline/execute
# ---------------------------------------------------------------------------

class TestExecutePipeline:
    def test_returns_session_id_and_result(self, client, mock_orchestrator):
        resp = client.post("/api/pipeline/execute", json=_pipeline_config_dict())
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "COMPLETED"
        assert data["output"] == "result-output"
        assert data["execution_order"] == ["agent-1"]
        assert data["execution_time_ms"] == 42.0
        assert data["error"] is None

    def test_creates_session_in_store(self, client, mock_orchestrator):
        resp = client.post("/api/pipeline/execute", json=_pipeline_config_dict())
        session_id = resp.json()["session_id"]
        assert session_id in _sessions

    def test_calls_orchestrator_run_pipeline(self, client, mock_orchestrator):
        client.post("/api/pipeline/execute", json=_pipeline_config_dict())
        mock_orchestrator.run_pipeline.assert_called_once()

    def test_failed_pipeline_returns_failed_status(self, client, mock_orchestrator):
        mock_orchestrator.run_pipeline = AsyncMock(
            return_value=(
                PipelineResult(
                    status="FAILED",
                    error="agent crashed",
                    failed_agent="agent-1",
                    failed_step=0,
                ),
                None,
            )
        )
        resp = client.post("/api/pipeline/execute", json=_pipeline_config_dict())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "FAILED"
        assert data["error"] == "agent crashed"

    def test_exception_returns_500(self, client, mock_orchestrator):
        mock_orchestrator.run_pipeline = AsyncMock(side_effect=RuntimeError("unexpected"))
        resp = client.post("/api/pipeline/execute", json=_pipeline_config_dict())
        assert resp.status_code == 500
        assert "Pipeline execution failed" in resp.json()["detail"]

    def test_multi_agent_pipeline(self, client, mock_orchestrator):
        mock_orchestrator.run_pipeline = AsyncMock(
            return_value=(
                PipelineResult(
                    status="COMPLETED",
                    output="final",
                    execution_order=["a1", "a2", "a3"],
                    execution_time_ms=100.0,
                ),
                None,
            )
        )
        resp = client.post(
            "/api/pipeline/execute",
            json=_pipeline_config_dict(["a1", "a2", "a3"]),
        )
        data = resp.json()
        assert data["execution_order"] == ["a1", "a2", "a3"]


# ---------------------------------------------------------------------------
# WS /api/ws/execution/{session_id}
# ---------------------------------------------------------------------------

class TestWsExecution:
    def test_ws_unknown_session_returns_error(self, app):
        client = TestClient(app)
        with client.websocket_connect("/api/ws/execution/nonexistent") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Session not found" in msg["detail"]

    def test_ws_streams_pipeline_complete(self, app, mock_orchestrator):
        session = _create_session("user-1", "test-pipeline")
        config = _pipeline_config()
        store_session_config(session.id, config)

        client = TestClient(app)
        with client.websocket_connect(f"/api/ws/execution/{session.id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "pipeline_complete"
            assert msg["session_id"] == session.id
            assert msg["status"] == "COMPLETED"

    def test_ws_calls_stream_pipeline(self, app, mock_orchestrator):
        session = _create_session("user-1", "test-pipeline")
        config = _pipeline_config()
        store_session_config(session.id, config)

        client = TestClient(app)
        with client.websocket_connect(f"/api/ws/execution/{session.id}") as ws:
            ws.receive_json()

        mock_orchestrator.stream_pipeline.assert_called_once()

    def test_ws_no_config_returns_error(self, app, mock_orchestrator):
        session = _create_session("user-1", "test-pipeline")

        client = TestClient(app)
        with client.websocket_connect(f"/api/ws/execution/{session.id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "No pipeline config" in msg["detail"]

    def test_ws_exception_sends_error_event(self, app, mock_orchestrator):
        mock_orchestrator.stream_pipeline = AsyncMock(
            side_effect=RuntimeError("kaboom")
        )
        session = _create_session("user-1", "test-pipeline")
        store_session_config(session.id, _pipeline_config())

        client = TestClient(app)
        with client.websocket_connect(f"/api/ws/execution/{session.id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "kaboom" in msg["detail"]

        assert _sessions[session.id].status == "failed"
