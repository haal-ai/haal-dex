"""Integration tests for WebSocket streaming — chat and execution events.

Validates: Requirements 17.1, 17.2, 3.1, 3.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.chat import set_chat_agent, _conversations
from app.api.pipeline import _sessions, _session_configs, store_session_config
from app.engine.graph_factory import PipelineResult
from app.models.session import Session
from tests.integration.conftest import make_pipeline_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_session_in_store(user_id: str = "user-001") -> Session:
    """Create a session directly in the in-memory store."""
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        pipeline_config_id="test-pipeline",
        status="pending",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        input_files=[],
        output_documents=[],
    )
    _sessions[session.id] = session
    return session


class _MockChatAgent:
    """Mock chat agent that echoes back a predictable response."""

    async def respond(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"Echo: {last}"


class TestChatWebSocket:
    """Chat WebSocket streaming tests.

    Validates: Requirements 17.1 (LLM response streaming via WebSocket)
    """

    @pytest.fixture(autouse=True)
    def _setup_chat(self):
        """Install mock chat agent and clear conversations."""
        set_chat_agent(_MockChatAgent())
        _conversations.clear()
        yield
        _conversations.clear()
        set_chat_agent(None)

    def test_chat_sends_tokens_then_response(self, client: TestClient):
        """Client sends a message, receives chat_token events then chat_response."""
        with client.websocket_connect("/api/ws/chat/session-1") as ws:
            ws.send_json({"type": "message", "content": "Hello"})

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            # Should have at least one chat_token and one chat_response
            token_msgs = [m for m in messages if m["type"] == "chat_token"]
            response_msgs = [m for m in messages if m["type"] == "chat_response"]
            assert len(token_msgs) >= 1
            assert len(response_msgs) == 1
            assert "Echo: Hello" in response_msgs[0]["content"]

    def test_chat_maintains_session_context(self, client: TestClient):
        """Multiple messages in the same session accumulate context."""
        with client.websocket_connect("/api/ws/chat/session-ctx") as ws:
            # Send first message
            ws.send_json({"type": "message", "content": "First"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

            # Send second message
            ws.send_json({"type": "message", "content": "Second"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

        # Verify context has both messages
        ctx = _conversations.get("session-ctx")
        assert ctx is not None
        assert len(ctx.messages) == 4  # 2 user + 2 assistant

    def test_chat_unknown_type_returns_error(self, client: TestClient):
        """Sending an unknown message type returns an error event."""
        with client.websocket_connect("/api/ws/chat/session-err") as ws:
            ws.send_json({"type": "unknown", "content": "x"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Unknown message type" in msg["content"]


class TestExecutionWebSocket:
    """Execution WebSocket streaming tests.

    Validates: Requirements 17.2 (pipeline streaming via WebSocket)
    """

    def test_ws_execution_streams_pipeline_complete(
        self, client: TestClient, mock_orchestrator
    ):
        """WebSocket receives pipeline_complete event after execution."""
        session = _create_session_in_store()
        store_session_config(session.id, make_pipeline_config())

        with client.websocket_connect(
            f"/api/ws/execution/{session.id}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "pipeline_complete"
            assert msg["status"] == "COMPLETED"
            assert msg["session_id"] == session.id

    def test_ws_execution_unknown_session(self, client: TestClient):
        """Connecting with an unknown session_id returns an error."""
        with client.websocket_connect(
            "/api/ws/execution/nonexistent"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Session not found" in msg["detail"]

    def test_ws_execution_no_config_returns_error(
        self, client: TestClient, mock_orchestrator
    ):
        """Session exists but no config stored → error."""
        session = _create_session_in_store()
        # Don't store config

        with client.websocket_connect(
            f"/api/ws/execution/{session.id}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "No pipeline config" in msg["detail"]

    def test_ws_execution_failure_sends_error(
        self, client: TestClient, mock_orchestrator
    ):
        """Pipeline exception is forwarded as an error event."""
        mock_orchestrator.stream_pipeline = AsyncMock(
            side_effect=RuntimeError("agent exploded")
        )
        session = _create_session_in_store()
        store_session_config(session.id, make_pipeline_config())

        with client.websocket_connect(
            f"/api/ws/execution/{session.id}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "agent exploded" in msg["detail"]

        # Session should be marked as failed
        assert _sessions[session.id].status == "failed"

    def test_ws_execution_multi_agent_reports_all(
        self, client: TestClient, mock_orchestrator
    ):
        """Multi-agent pipeline reports all agents in execution_order."""
        mock_orchestrator.stream_pipeline = AsyncMock(
            return_value=(
                PipelineResult(
                    status="COMPLETED",
                    output="done",
                    execution_order=["a1", "a2"],
                    execution_time_ms=80.0,
                ),
                None,
            )
        )
        session = _create_session_in_store()
        store_session_config(session.id, make_pipeline_config(["a1", "a2"]))

        with client.websocket_connect(
            f"/api/ws/execution/{session.id}"
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "pipeline_complete"
            assert msg["execution_order"] == ["a1", "a2"]
