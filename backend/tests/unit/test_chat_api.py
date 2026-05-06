"""Unit tests for the chat WebSocket endpoint.

Requirements: 1.1, 1.2, 1.4, 1.6, 1.11, 2.1, 2.3, 2.4, 17.1
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path

from app.api.chat import (
    ChatMessage,
    ConversationContext,
    _conversations,
    _DefaultChatAgent,
    get_chat_agent,
    get_conversations,
    router,
    set_chat_agent,
    set_memory_manager,
    _get_or_create_context,
)
from app.services.memory_manager import MemoryManager


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
def _clear_state(tmp_path: Path):
    """Reset conversation store, agent, and memory manager before each test."""
    _conversations.clear()
    set_chat_agent(_FakeAgent())
    set_memory_manager(MemoryManager(storage_dir=tmp_path / "chat_sessions"))
    yield
    _conversations.clear()
    set_chat_agent(None)  # type: ignore[arg-type]
    set_memory_manager(None)


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


# ---------------------------------------------------------------------------
# Retrieval integration tests — Requirements 5.1, 5.3, 5.6
# ---------------------------------------------------------------------------

from app.api.chat import (
    _build_retrieval_router,
    _create_retrieval_backend,
    ConversationContext as _ConversationContext,
)
from app.engine.retrieval_router import RetrievalRouter, RetrievalResult
from app.models.personality import (
    Personality,
    PersonalityAccess,
    RetrievalBackendConfig,
    RetrievalACLEntry,
)


class _FakeRetrievalBackend:
    """Fake retrieval backend that returns canned results."""

    def __init__(self, results=None):
        self._results = results or []
        self.last_query = None

    async def query(self, query_text: str, top_k: int = 5):
        self.last_query = query_text
        return self._results[:top_k]


class _FakeResult:
    """Mimics a backend result object."""

    def __init__(self, document_fragment: str, score: float, source: str):
        self.document_fragment = document_fragment
        self.score = score
        self.source = source


class _RetrievalCapturingAgent:
    """Agent that captures the messages it receives, including system messages."""

    def __init__(self):
        self.last_messages = []

    async def respond(self, messages: list[dict[str, str]]) -> str:
        self.last_messages = list(messages)
        last = messages[-1]["content"] if messages else ""
        return f"echo: {last}"


class TestBuildRetrievalRouter:
    """Tests for _build_retrieval_router helper."""

    def test_returns_none_when_no_backends(self):
        """Requirement 5.6: skip retrieval when no backends configured."""
        personality = Personality(
            id="test",
            name="Test",
            description="",
            system_prompt="You are a test bot.",
            retrieval_backends=[],
        )
        router = _build_retrieval_router(personality)
        assert router is None

    def test_returns_none_when_all_backends_fail_to_create(self):
        """If all backend configs are invalid, return None."""
        personality = Personality(
            id="test",
            name="Test",
            description="",
            system_prompt="You are a test bot.",
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    name="bad-sqlite",
                    # Missing db_path and fts_table
                ),
            ],
        )
        router = _build_retrieval_router(personality)
        assert router is None

    def test_returns_router_with_valid_sqlite_backend(self, tmp_path):
        """Creates a router when a valid SQLite backend config is provided."""
        import sqlite3

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(content)")
        conn.close()

        personality = Personality(
            id="test",
            name="Test",
            description="",
            system_prompt="You are a test bot.",
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    db_path=db_path,
                    fts_table="docs",
                    name="test-sqlite",
                ),
            ],
        )
        router = _build_retrieval_router(personality)
        assert router is not None
        assert isinstance(router, RetrievalRouter)

    def test_passes_acl_to_router(self, tmp_path):
        """ACL from personality access is passed to the router."""
        import sqlite3

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(content)")
        conn.close()

        acl = [RetrievalACLEntry(backend_type="sqlite_bm25", index_name="test-sqlite")]
        personality = Personality(
            id="test",
            name="Test",
            description="",
            system_prompt="You are a test bot.",
            access=PersonalityAccess(allowed_retrieval_indexes=acl),
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    db_path=db_path,
                    fts_table="docs",
                    name="test-sqlite",
                ),
            ],
        )
        router = _build_retrieval_router(personality)
        assert router is not None
        assert router._acl is acl


class TestCreateRetrievalBackend:
    """Tests for _create_retrieval_backend helper."""

    def test_unknown_backend_type_returns_none(self):
        cfg = RetrievalBackendConfig(backend_type="unknown_type", name="bad")
        result = _create_retrieval_backend(cfg)
        assert result is None

    def test_sqlite_missing_db_path_returns_none(self):
        cfg = RetrievalBackendConfig(
            backend_type="sqlite_bm25", fts_table="docs", name="no-db"
        )
        result = _create_retrieval_backend(cfg)
        assert result is None

    def test_sqlite_missing_fts_table_returns_none(self):
        cfg = RetrievalBackendConfig(
            backend_type="sqlite_bm25", db_path="/tmp/test.db", name="no-fts"
        )
        result = _create_retrieval_backend(cfg)
        assert result is None

    def test_sqlite_valid_config_creates_backend(self, tmp_path):
        import sqlite3

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(content)")
        conn.close()

        cfg = RetrievalBackendConfig(
            backend_type="sqlite_bm25",
            db_path=db_path,
            fts_table="docs",
            name="test-sqlite",
        )
        result = _create_retrieval_backend(cfg)
        assert result is not None

    def test_bedrock_missing_index_path_returns_none(self):
        cfg = RetrievalBackendConfig(
            backend_type="bedrock_embedding",
            embedding_model="amazon.titan-embed-text-v2:0",
            name="no-index",
        )
        result = _create_retrieval_backend(cfg)
        assert result is None

    def test_bedrock_missing_embedding_model_returns_none(self):
        cfg = RetrievalBackendConfig(
            backend_type="bedrock_embedding",
            index_path="/tmp/test.index",
            name="no-model",
        )
        result = _create_retrieval_backend(cfg)
        assert result is None


class TestRetrievalIntegrationInChat:
    """Tests for retrieval integration in the WebSocket chat flow."""

    def test_no_retrieval_when_no_router(self, app):
        """Requirement 5.6: no retrieval when no backends configured.

        The _FakeAgent used in tests has no retrieval router, so the
        retrieval step is a no-op.
        """
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/no-retrieval") as ws:
            ws.send_json({"type": "message", "content": "hello"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "echo: hello"

        # Verify no router was set on the context
        ctx = _conversations["no-retrieval"]
        assert ctx.retrieval_router is None

    def test_retrieval_injects_context_into_agent_messages(self, app):
        """Requirement 5.1, 5.3: retrieval results injected into agent context."""
        # Create a capturing agent to inspect messages
        capturing_agent = _RetrievalCapturingAgent()
        set_chat_agent(capturing_agent)

        # Manually set up a context with a retrieval router
        ctx = _get_or_create_context("retrieval-session")
        ctx.agent = capturing_agent
        ctx.system_prompt = "You are a helpful assistant."

        # Create a router with a fake backend
        fake_backend = _FakeRetrievalBackend(
            results=[
                _FakeResult("Relevant document content", 0.95, "doc1.txt"),
            ]
        )
        ctx.retrieval_router = RetrievalRouter(
            backends=[("test-backend", fake_backend)]
        )

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/retrieval-session") as ws:
            ws.send_json({"type": "message", "content": "search query"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

        # Verify the agent received a system message with retrieval context
        assert len(capturing_agent.last_messages) >= 2
        system_msg = capturing_agent.last_messages[0]
        assert system_msg["role"] == "system"
        assert "Retrieved Context" in system_msg["content"]
        assert "Relevant document content" in system_msg["content"]

    def test_retrieval_skipped_when_no_results(self, app):
        """When retrieval returns empty results, no system message is injected."""
        capturing_agent = _RetrievalCapturingAgent()
        set_chat_agent(capturing_agent)

        ctx = _get_or_create_context("empty-retrieval")
        ctx.agent = capturing_agent
        ctx.system_prompt = "You are a helpful assistant."

        # Router with a backend that returns no results
        fake_backend = _FakeRetrievalBackend(results=[])
        ctx.retrieval_router = RetrievalRouter(
            backends=[("empty-backend", fake_backend)]
        )

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/empty-retrieval") as ws:
            ws.send_json({"type": "message", "content": "hello"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

        # No system message should be injected when results are empty
        roles = [m["role"] for m in capturing_agent.last_messages]
        assert "system" not in roles

    def test_retrieval_failure_does_not_break_chat(self, app):
        """Requirement 5.4: if retrieval fails, agent responds without context."""

        class _FailingBackend:
            async def query(self, query_text, top_k=5):
                raise RuntimeError("Backend exploded")

        capturing_agent = _RetrievalCapturingAgent()
        set_chat_agent(capturing_agent)

        ctx = _get_or_create_context("failing-retrieval")
        ctx.agent = capturing_agent
        ctx.system_prompt = "You are a helpful assistant."
        ctx.retrieval_router = RetrievalRouter(
            backends=[("failing-backend", _FailingBackend())]
        )

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/failing-retrieval") as ws:
            ws.send_json({"type": "message", "content": "hello"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

        # Chat should still work despite retrieval failure
        response = [m for m in messages if m["type"] == "chat_response"][0]
        assert response["content"] == "echo: hello"

    def test_context_stores_router_and_system_prompt(self):
        """ConversationContext stores retrieval_router and system_prompt fields."""
        ctx = _ConversationContext(session_id="test")
        assert ctx.retrieval_router is None
        assert ctx.system_prompt == ""

        router = RetrievalRouter(backends=[])
        ctx.retrieval_router = router
        ctx.system_prompt = "You are a bot."
        assert ctx.retrieval_router is router
        assert ctx.system_prompt == "You are a bot."


# ---------------------------------------------------------------------------
# Escalation integration tests — Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.7
# ---------------------------------------------------------------------------

from app.engine.escalation_detector import EscalationDetector


class _FallbackAgent:
    """Agent that identifies itself as the fallback."""

    async def respond(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"fallback: {last}"


class _EmptyResponseAgent:
    """Agent that returns an empty string."""

    async def respond(self, messages: list[dict[str, str]]) -> str:
        return ""


class _FailOnceAgent:
    """Agent that fails on the first call, then succeeds."""

    def __init__(self):
        self._call_count = 0

    async def respond(self, messages: list[dict[str, str]]) -> str:
        self._call_count += 1
        if self._call_count == 1:
            raise RuntimeError("primary model error")
        last = messages[-1]["content"] if messages else ""
        return f"recovered: {last}"


class TestEscalationIntegration:
    """Tests for EscalationDetector integration in the chat WebSocket flow."""

    def test_no_escalation_for_simple_message(self, app):
        """Requirement 6.2: simple messages route to primary model.

        When using a test agent override, escalation is skipped entirely
        because there is no fallback agent.
        """
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/simple-esc") as ws:
            ws.send_json({"type": "message", "content": "hello"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "echo: hello"
            # No fallback_used flag when primary handles it
            assert "fallback_used" not in response

    def test_escalation_routes_to_fallback_agent(self, app):
        """Requirement 6.3: complex messages route to fallback model.

        Set up a context with an escalation detector (low threshold) and
        a fallback agent. A message with a complexity keyword should
        trigger escalation.
        """
        primary = _FakeAgent()
        fallback = _FallbackAgent()
        set_chat_agent(primary)

        ctx = _get_or_create_context("esc-fallback")
        ctx.agent = primary
        ctx.fallback_agent = fallback
        ctx.escalation_detector = EscalationDetector(
            length_threshold=5000,
            complexity_keywords=["analyze"],
            context_depth_threshold=100,
        )

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/esc-fallback") as ws:
            ws.send_json({"type": "message", "content": "please analyze this code"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "fallback: please analyze this code"
            assert response.get("fallback_used") is True

    def test_fallback_used_flag_not_present_when_primary_handles(self, app):
        """Requirement 6.7: fallback_used flag only present when fallback is used."""
        primary = _FakeAgent()
        fallback = _FallbackAgent()
        set_chat_agent(primary)

        ctx = _get_or_create_context("no-esc")
        ctx.agent = primary
        ctx.fallback_agent = fallback
        ctx.escalation_detector = EscalationDetector(
            length_threshold=5000,
            complexity_keywords=["analyze"],
            context_depth_threshold=100,
        )

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/no-esc") as ws:
            ws.send_json({"type": "message", "content": "hello"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "echo: hello"
            assert "fallback_used" not in response

    def test_primary_error_retries_with_fallback(self, app):
        """Requirement 6.4: primary model error triggers fallback retry."""
        primary = _ErrorAgent()
        fallback = _FallbackAgent()
        set_chat_agent(primary)

        ctx = _get_or_create_context("err-retry")
        ctx.agent = primary
        ctx.fallback_agent = fallback
        # No escalation detector needed — error retry is independent

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/err-retry") as ws:
            ws.send_json({"type": "message", "content": "test retry"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "fallback: test retry"
            assert response.get("fallback_used") is True

    def test_empty_response_retries_with_fallback(self, app):
        """Requirement 6.4: empty primary response triggers fallback retry."""
        primary = _EmptyResponseAgent()
        fallback = _FallbackAgent()
        set_chat_agent(primary)

        ctx = _get_or_create_context("empty-retry")
        ctx.agent = primary
        ctx.fallback_agent = fallback

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/empty-retry") as ws:
            ws.send_json({"type": "message", "content": "test empty"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "fallback: test empty"
            assert response.get("fallback_used") is True

    def test_both_models_fail_returns_structured_error(self, app):
        """Requirement 6.5: both models fail returns structured error."""
        primary = _ErrorAgent()
        fallback = _ErrorAgent()
        set_chat_agent(primary)

        ctx = _get_or_create_context("both-fail")
        ctx.agent = primary
        ctx.fallback_agent = fallback

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/both-fail") as ws:
            ws.send_json({"type": "message", "content": "doom"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "Both primary and fallback models failed" in msg["content"]

    def test_escalation_skipped_for_test_agent_override(self, app):
        """When test agent override is set, escalation logic is skipped.

        The _FakeAgent has no escalation_detector or fallback_agent on
        the context, so escalation is naturally skipped.
        """
        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/test-override") as ws:
            # Even with a complexity keyword, the test agent handles it
            ws.send_json({"type": "message", "content": "analyze this"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            response = [m for m in messages if m["type"] == "chat_response"][0]
            assert response["content"] == "echo: analyze this"
            assert "fallback_used" not in response

    def test_context_stores_escalation_detector_and_fallback_agent(self):
        """ConversationContext stores escalation_detector and fallback_agent fields."""
        ctx = _ConversationContext(session_id="test-esc")
        assert ctx.escalation_detector is None
        assert ctx.fallback_agent is None

        detector = EscalationDetector()
        fallback = _FallbackAgent()
        ctx.escalation_detector = detector
        ctx.fallback_agent = fallback
        assert ctx.escalation_detector is detector
        assert ctx.fallback_agent is fallback

    def test_primary_error_no_fallback_returns_error(self, app):
        """When primary fails and no fallback is available, return error."""
        set_chat_agent(_ErrorAgent())

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/no-fallback-err") as ws:
            ws.send_json({"type": "message", "content": "boom"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "agent exploded" in msg["content"]

# ---------------------------------------------------------------------------
# Personality switching tests — Requirements 10.1, 10.2, 10.3, 10.4, 10.5
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
from app.models.personality import ModelConfig


def _make_personality(pid: str, name: str = "", system_prompt: str = "You are helpful.") -> Personality:
    """Create a minimal Personality for testing."""
    return Personality(
        id=pid,
        name=name or pid,
        description=f"Test personality {pid}",
        system_prompt=system_prompt,
        access=PersonalityAccess(allowed_tools=[]),
    )


class _TrackingFakeStore:
    """Fake PersonalityStore that returns configured personalities."""

    def __init__(self, personalities: dict[str, Personality]):
        self._personalities = personalities

    def get(self, personality_id: str) -> Personality | None:
        return self._personalities.get(personality_id)

    def list(self) -> list[Personality]:
        return list(self._personalities.values())

    @property
    def base_dir(self) -> Path:
        return Path(".")


class TestPersonalitySwitching:
    """Tests for personality switching in the WebSocket handler."""

    def test_switch_preserves_conversation_history(self, app, monkeypatch):
        """Requirement 10.3: switching personality preserves messages."""
        p_default = _make_personality("default", system_prompt="Default bot.")
        p_expert = _make_personality("expert", system_prompt="Expert bot.")
        fake_store = _TrackingFakeStore({"default": p_default, "expert": p_expert})
        new_agent = _FakeAgent()

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)
        monkeypatch.setattr("app.api.chat._try_create_strands_agent", lambda **kw: new_agent)
        monkeypatch.setattr("app.api.chat._try_create_fallback_agent", lambda **kw: None)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-preserve") as ws:
            # Send first message with default personality
            ws.send_json({"type": "message", "content": "hello"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

            # Now switch personality
            ws.send_json({"type": "message", "content": "world", "personality_id": "expert"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

        # Verify conversation history was preserved (not cleared)
        ctx = _conversations["switch-preserve"]
        # Should have: user("hello"), assistant(...), user("world"), assistant(...)
        assert len(ctx.messages) == 4
        assert ctx.messages[0].role == "user"
        assert ctx.messages[0].content == "hello"
        assert ctx.messages[2].role == "user"
        assert ctx.messages[2].content == "world"

    def test_switch_sends_personality_changed_event(self, app, monkeypatch):
        """Requirement 10.5: metadata event sent on personality change."""
        p_default = _make_personality("default")
        p_expert = _make_personality("expert")
        fake_store = _TrackingFakeStore({"default": p_default, "expert": p_expert})
        new_agent = _FakeAgent()

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)
        monkeypatch.setattr("app.api.chat._try_create_strands_agent", lambda **kw: new_agent)
        monkeypatch.setattr("app.api.chat._try_create_fallback_agent", lambda **kw: None)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-event") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "expert"})

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            changed_events = [m for m in messages if m["type"] == "personality_changed"]
            assert len(changed_events) == 1
            assert changed_events[0]["personality_id"] == "expert"
            assert changed_events[0]["session_id"] == "switch-event"

    def test_switch_to_unknown_personality_returns_error(self, app, monkeypatch):
        """Requirement 10.4: unknown personality_id returns error."""
        p_default = _make_personality("default")
        fake_store = _TrackingFakeStore({"default": p_default})

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-unknown") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "nonexistent"})

            # First we get the error about personality not found,
            # then the message is still processed with the current agent
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            error_msgs = [m for m in messages if m["type"] == "error"]
            assert any("Personality 'nonexistent' not found" in m["content"] for m in error_msgs)

    def test_switch_unknown_personality_keeps_current(self, app, monkeypatch):
        """Requirement 10.4: unknown personality keeps current personality active."""
        p_default = _make_personality("default")
        fake_store = _TrackingFakeStore({"default": p_default})

        ctx = _get_or_create_context("switch-keep")
        ctx.personality_id = "default"

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-keep") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "nonexistent"})

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

        ctx = _conversations["switch-keep"]
        assert ctx.personality_id == "default"

    def test_switch_updates_personality_id_in_context(self, app, monkeypatch):
        """Requirement 10.1: context.personality_id updated on switch."""
        p_default = _make_personality("default")
        p_expert = _make_personality("expert")
        fake_store = _TrackingFakeStore({"default": p_default, "expert": p_expert})
        new_agent = _FakeAgent()

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)
        monkeypatch.setattr("app.api.chat._try_create_strands_agent", lambda **kw: new_agent)
        monkeypatch.setattr("app.api.chat._try_create_fallback_agent", lambda **kw: None)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-update") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "expert"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

        ctx = _conversations["switch-update"]
        assert ctx.personality_id == "expert"

    def test_no_switch_when_same_personality(self, app, monkeypatch):
        """No personality_changed event when personality_id matches current."""
        p_default = _make_personality("default")
        fake_store = _TrackingFakeStore({"default": p_default})

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/no-switch") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "default"})
            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "chat_response":
                    break

            changed_events = [m for m in messages if m["type"] == "personality_changed"]
            assert len(changed_events) == 0

    def test_switch_reinitializes_agent(self, app, monkeypatch):
        """Requirement 10.2: agent is reinitialized on personality switch."""
        p_default = _make_personality("default")
        p_expert = _make_personality("expert", system_prompt="Expert system prompt.")
        fake_store = _TrackingFakeStore({"default": p_default, "expert": p_expert})

        ctx = _get_or_create_context("switch-reinit")
        old_agent = _FakeAgent()
        ctx.agent = old_agent
        ctx.personality_id = "default"

        new_agent = _FakeAgent()

        monkeypatch.setattr("app.api.chat._get_personality_store", lambda: fake_store)
        monkeypatch.setattr("app.api.chat._try_create_strands_agent", lambda **kw: new_agent)
        monkeypatch.setattr("app.api.chat._try_create_fallback_agent", lambda **kw: None)

        client = TestClient(app)
        with client.websocket_connect("/api/ws/chat/switch-reinit") as ws:
            ws.send_json({"type": "message", "content": "hi", "personality_id": "expert"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "chat_response":
                    break

        ctx = _conversations["switch-reinit"]
        assert ctx.agent is not old_agent
