"""Unit tests for the chat WebSocket endpoint.

Requirements: 2.1, 2.3, 2.4, 17.1
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import (
    ChatMessage,
    ConversationContext,
    _conversations,
    _DefaultChatAgent,
    get_chat_agent,
    get_conversations,
    router,
    set_chat_agent,
    _get_or_create_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAgent:
    """Deterministic agent for testing."""

    async def respond(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"echo: {last}"


class _ErrorAgent:
    """Agent that always raises."""

    async def respond(self, messages: list[dict[str, str]]) -> str:
        raise RuntimeError("agent exploded")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_state():
    """Reset conversation store and agent before each test."""
    _conversations.clear()
    set_chat_agent(_FakeAgent())
    yield
    _conversations.clear()
    set_chat_agent(None)  # type: ignore[arg-type]


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# ConversationContext unit tests
# ---------------------------------------------------------------------------


class TestConversationContext:
    def test_get_or_create_creates_new(self):
        ctx = _get_or_create_context("s1")
        assert ctx.session_id == "s1"
        assert ctx.messages == []

    def test_get_or_create_returns_existing(self):
        ctx1 = _get_or_create_context("s1")
        ctx1.messages.append(ChatMessage(role="user", content="hi"))
        ctx2 = _get_or_create_context("s1")
        assert ctx2 is ctx1
        assert len(ctx2.messages) == 1

    def test_get_conversations_returns_store(self):
        assert get_conversations() is _conversations

    def test_separate_sessions_have_separate_contexts(self):
        ctx1 = _get_or_create_context("s1")
        ctx2 = _get_or_create_context("s2")
        ctx1.messages.append(ChatMessage(role="user", content="a"))
        assert len(ctx2.messages) == 0


# ---------------------------------------------------------------------------
# WebSocket chat tests
# ---------------------------------------------------------------------------


class TestWsChat:
    def test_send_message_receives_tokens_and_response(self, app):
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/session-1") as ws:
            ws.send_json({"type": "message", "content": "hello"})

            # Collect all messages until we get the chat_response
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
            assert response_msgs[0]["content"] == "echo: hello"
            assert response_msgs[0]["session_id"] == "session-1"

    def test_session_id_in_all_responses(self, app):
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/my-session") as ws:
            ws.send_json({"type": "message", "content": "test"})

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            for msg in messages:
                assert msg["session_id"] == "my-session"

    def test_conversation_context_maintained(self, app):
        """Multiple messages in the same session accumulate context."""
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/ctx-session") as ws:
            # First message
            ws.send_json({"type": "message", "content": "first"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

            # Second message
            ws.send_json({"type": "message", "content": "second"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

        ctx = _conversations["ctx-session"]
        assert len(ctx.messages) == 4  # 2 user + 2 assistant
        assert ctx.messages[0].role == "user"
        assert ctx.messages[0].content == "first"
        assert ctx.messages[1].role == "assistant"
        assert ctx.messages[2].role == "user"
        assert ctx.messages[2].content == "second"
        assert ctx.messages[3].role == "assistant"

    def test_unknown_message_type_returns_error(self, app):
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/session-err") as ws:
            ws.send_json({"type": "unknown_type", "content": "x"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Unknown message type" in msg["content"]

    def test_agent_error_returns_error_event(self, app):
        set_chat_agent(_ErrorAgent())
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/session-agent-err") as ws:
            ws.send_json({"type": "message", "content": "boom"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "agent exploded" in msg["content"]

    def test_agent_error_records_user_message_in_context(self, app):
        """Even when the agent fails, the user message is recorded."""
        set_chat_agent(_ErrorAgent())
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/session-ctx-err") as ws:
            ws.send_json({"type": "message", "content": "boom"})
            ws.receive_json()  # consume error

        ctx = _conversations["session-ctx-err"]
        assert len(ctx.messages) == 1
        assert ctx.messages[0].role == "user"
        assert ctx.messages[0].content == "boom"

    def test_tokens_concatenate_to_full_response(self, app):
        """Token contents joined together should equal the full response."""
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/tok-session") as ws:
            ws.send_json({"type": "message", "content": "hi"})

            tokens = []
            full_response = None
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_token":
                    tokens.append(msg["content"])
                elif msg["type"] == "chat_response":
                    full_response = msg["content"]
                    break

            reconstructed = "".join(tokens)
            assert reconstructed == full_response

    def test_multiple_sessions_independent(self, app):
        """Two different session_ids maintain independent contexts."""
        client = TestClient(app)

        with client.websocket_connect("/api/ws/chat/s1") as ws:
            ws.send_json({"type": "message", "content": "msg-s1"})
            while True:
                if ws.receive_json()["type"] == "chat_response":
                    break

        with client.websocket_connect("/api/ws/chat/s2") as ws:
            ws.send_json({"type": "message", "content": "msg-s2"})
            while True:
                if ws.receive_json()["type"] == "chat_response":
                    break

        assert len(_conversations["s1"].messages) == 2
        assert len(_conversations["s2"].messages) == 2
        assert _conversations["s1"].messages[0].content == "msg-s1"
        assert _conversations["s2"].messages[0].content == "msg-s2"


# ---------------------------------------------------------------------------
# DefaultChatAgent tests
# ---------------------------------------------------------------------------


class TestDefaultChatAgent:
    @pytest.mark.asyncio
    async def test_default_agent_echoes_last_message(self):
        agent = _DefaultChatAgent()
        result = await agent.respond([{"role": "user", "content": "hello world"}])
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_default_agent_empty_messages(self):
        agent = _DefaultChatAgent()
        result = await agent.respond([])
        assert isinstance(result, str)
