"""Shared fixtures for backend integration tests.

Provides a fully wired FastAPI TestClient with mock LLM providers,
auth helpers, and test data factories.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.engine.agent_factory import AgentFactory
from app.engine.graph_factory import GraphFactory, PipelineResult
from app.engine.model_factory import ModelFactory
from app.main import create_app
from app.models.auth import UserContext
from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.models.session import Session
from app.models.templates import DocumentMetadata, RenderedDocument
from app.pipeline_orchestrator import PipelineOrchestrator
from app.services.encryption_service import EncryptionService
from app.services.execution_logger import ExecutionLogger
from app.services.metrics_collector import MetricsCollector
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

ADMIN_CREDS = {"username": "admin", "password": "admin"}
USER_CREDS = {"username": "user", "password": "user"}


def login(client: TestClient, creds: dict) -> str:
    """Login and return the access token."""
    resp = client.post("/api/auth/login", json=creds)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    """Return an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------

def make_provider_config() -> ProviderConfig:
    return ProviderConfig(provider_type="bedrock", model_id="claude-3-sonnet")


def make_agent_config(name: str = "agent-1") -> AgentConfig:
    return AgentConfig(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=make_provider_config(),
        description=f"Agent {name}",
    )


def make_pipeline_config(agent_names: list[str] | None = None) -> PipelineConfig:
    names = agent_names or ["agent-1"]
    return PipelineConfig(
        name="test-pipeline",
        agents=[make_agent_config(n) for n in names],
        output=OutputConfig(template="default", formats=["md"]),
    )


def make_pipeline_config_dict(agent_names: list[str] | None = None) -> dict:
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
        "output": {"template": "default", "formats": ["md"]},
    }


# ---------------------------------------------------------------------------
# Mock orchestrator factory
# ---------------------------------------------------------------------------

def _make_mock_orchestrator() -> MagicMock:
    """Return a PipelineOrchestrator mock with sensible defaults."""
    orch = MagicMock(spec=PipelineOrchestrator)

    def _create_session(user_id, config):
        return Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            pipeline_config_id=config.name,
            status="pending",
            created_at=datetime.now(timezone.utc),
            completed_at=None,
            input_files=[],
            output_documents=[],
        )

    orch.create_session = MagicMock(side_effect=_create_session)
    orch.run_pipeline = AsyncMock(
        return_value=(
            PipelineResult(
                status="COMPLETED",
                output="pipeline-output",
                execution_order=["agent-1"],
                execution_time_ms=50.0,
            ),
            None,
        )
    )
    orch.stream_pipeline = AsyncMock(
        return_value=(
            PipelineResult(
                status="COMPLETED",
                output="streamed-output",
                execution_order=["agent-1"],
                execution_time_ms=60.0,
            ),
            None,
        )
    )
    return orch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_orchestrator():
    return _make_mock_orchestrator()


@pytest.fixture()
def app(mock_orchestrator):
    """Create a fresh FastAPI app with mock orchestrator for pipeline endpoints."""
    from app.api.pipeline import _get_orchestrator, _sessions, _session_configs, _session_files

    application = create_app()
    application.dependency_overrides[_get_orchestrator] = lambda: mock_orchestrator

    # Clear in-memory stores
    _sessions.clear()
    _session_configs.clear()
    _session_files.clear()

    yield application

    _sessions.clear()
    _session_configs.clear()
    _session_files.clear()
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app) -> TestClient:
    """TestClient with the full app (no auth override — real JWT flow)."""
    return TestClient(app)


@pytest.fixture()
def admin_token(client) -> str:
    return login(client, ADMIN_CREDS)


@pytest.fixture()
def user_token(client) -> str:
    return login(client, USER_CREDS)
