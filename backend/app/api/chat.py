"""Chat WebSocket endpoint.

Provides:
- WS /api/ws/chat/{session_id} — bidirectional chat via WebSocket

Each session maintains a conversation history (list of messages).
When a message is received it is sent to a strands.Agent (or a mock
agent when the SDK is not installed) and the response is streamed
back token by token.

Conversation history is persisted via :class:`MemoryManager` so that
sessions survive reconnections and can be condensed when they grow
large.

Protocol:
  Client sends:  {"type": "message", "content": "user message"}
  Server sends:  {"type": "chat_token",    "content": "partial", "session_id": "..."}
  Server sends:  {"type": "chat_response", "content": "full response", "session_id": "..."}

Requirements: 1.1, 1.2, 1.4, 1.6, 1.11, 2.1, 2.3, 2.4, 17.1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.engine.agent_factory import AgentFactory
from app.engine.escalation_detector import EscalationDetector
from app.engine.model_factory import ModelFactory
from app.engine.chat_tools import CHAT_TOOLS
from app.engine.retrieval_router import RetrievalRouter
from app.engine.tools import ToolRegistry
from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.personality import Personality, RetrievalBackendConfig
from app.models.pipeline import AgentConfig
from app.services.environment_injector import EnvironmentInjector
from app.services.memory_manager import MemoryManager
from app.services.personality_store import PersonalityStore
from app.services.chat_provider_service import ChatProviderService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Memory manager (persistent conversation storage)
# ---------------------------------------------------------------------------

_DEFAULT_STORAGE_DIR = Path(__file__).resolve().parents[2] / "chat_sessions"

_memory_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Return the module-level MemoryManager, creating it lazily."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(storage_dir=_DEFAULT_STORAGE_DIR)
    return _memory_manager


def set_memory_manager(manager: MemoryManager | None) -> None:
    """Override the MemoryManager (useful for testing)."""
    global _memory_manager
    _memory_manager = manager


# ---------------------------------------------------------------------------
# Conversation context store  (session_id → ConversationContext)
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    """A single message in the conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class ConversationContext:
    """Holds the full conversation history for a session."""

    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    personality_id: str = "default"
    agent: Any | None = None
    fallback_agent: Any | None = None
    escalation_detector: EscalationDetector | None = None
    retrieval_router: RetrievalRouter | None = None
    system_prompt: str = ""


_conversations: dict[str, ConversationContext] = {}


def get_conversations() -> dict[str, ConversationContext]:
    """Return the shared conversation store (overridable in tests)."""
    return _conversations


def _get_or_create_context(session_id: str) -> ConversationContext:
    """Return existing context or create a new one for *session_id*."""
    if session_id not in _conversations:
        _conversations[session_id] = ConversationContext(session_id=session_id)
    return _conversations[session_id]


# ---------------------------------------------------------------------------
# Chat agent abstraction
# ---------------------------------------------------------------------------


class ChatAgent(Protocol):
    """Minimal interface for a chat agent."""

    async def respond(self, messages: list[dict[str, str]]) -> str: ...


class _DefaultChatAgent:
    """Fallback agent that echoes back a simple response.

    Used when the Strands SDK is not available or for lightweight testing.
    """

    async def respond(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"I received your message: {last}"


def _get_personality_store() -> PersonalityStore:
    backend_dir = Path(__file__).resolve().parents[2]
    store_path = backend_dir / "personalities_store.json"
    return PersonalityStore(store_path)


def _get_chat_provider_service() -> ChatProviderService:
    return ChatProviderService()


# Module-level EnvironmentInjector and ToolRegistry instances
_environment_injector = EnvironmentInjector()
_tool_registry = ToolRegistry()


def _build_retrieval_router(
    personality: Personality, base_dir: Path | None = None
) -> RetrievalRouter | None:
    """Create a RetrievalRouter from a personality's retrieval backend configs.

    Returns ``None`` when the personality has no retrieval backends configured
    (Requirement 5.6: skip retrieval when no backends configured).
    """
    if not personality.retrieval_backends:
        return None

    backends: list[tuple[str, Any]] = []
    for cfg in personality.retrieval_backends:
        backend = _create_retrieval_backend(cfg, base_dir=base_dir)
        if backend is not None:
            name = cfg.name or cfg.db_path or cfg.index_path or cfg.backend_type
            backends.append((name, backend))

    if not backends:
        return None

    acl = personality.access.allowed_retrieval_indexes
    return RetrievalRouter(backends=backends, acl=acl)


def _create_retrieval_backend(
    cfg: RetrievalBackendConfig, base_dir: Path | None = None
) -> Any | None:
    """Instantiate a single retrieval backend from its config.

    Returns ``None`` if the backend cannot be created (missing deps, etc.).
    Relative paths in *cfg* are resolved against *base_dir* when provided.
    """
    def _resolve(p: str | None) -> str | None:
        if p is None:
            return None
        path = Path(p)
        if not path.is_absolute() and base_dir is not None:
            path = (base_dir / path).resolve()
        return str(path)

    try:
        if cfg.backend_type == "sqlite_bm25":
            from app.engine.sqlite_bm25_backend import (
                SQLiteBM25Backend,
                _FTS5_AVAILABLE,
            )

            if not _FTS5_AVAILABLE:
                logger.warning(
                    "SQLite FTS5 extension unavailable; "
                    "skipping SQLite BM25 backend '%s'.",
                    cfg.name,
                )
                return None

            if not cfg.db_path or not cfg.fts_table:
                logger.warning(
                    "SQLite BM25 backend '%s' missing db_path or fts_table; skipping.",
                    cfg.name,
                )
                return None
            resolved_db = _resolve(cfg.db_path)
            logger.info("Creating SQLite BM25 backend '%s' at %s", cfg.name, resolved_db)
            return SQLiteBM25Backend(
                db_path=resolved_db,
                fts_table=cfg.fts_table,
                ranking_algorithm=cfg.ranking_algorithm,
                column_weights=cfg.column_weights,
            )

        if cfg.backend_type == "bedrock_embedding":
            from app.engine.bedrock_embedding_backend import BedrockEmbeddingBackend

            if not cfg.index_path or not cfg.embedding_model:
                logger.warning(
                    "Bedrock embedding backend '%s' missing index_path or embedding_model; skipping.",
                    cfg.name,
                )
                return None
            return BedrockEmbeddingBackend(
                model_id=cfg.embedding_model,
                index_path=_resolve(cfg.index_path),
                top_k=cfg.top_k,
            )

        logger.warning("Unknown retrieval backend type '%s'; skipping.", cfg.backend_type)
        return None
    except Exception as exc:
        logger.warning(
            "Failed to create retrieval backend '%s' (%s): %s",
            cfg.name,
            cfg.backend_type,
            exc,
        )
        return None


def _build_chat_agent_config(personality) -> AgentConfig:
    provider_config = _get_chat_provider_service().get_provider_config()
    system_prompt = personality.combined_system_prompt()
    return AgentConfig(
        name=f"chat-{personality.id}",
        model=f"{provider_config.provider_type}/{provider_config.model_id}",
        provider_config=provider_config,
        description=system_prompt,
        system_prompt=system_prompt,
        tools=list(personality.access.allowed_tools),
        faiss_indexes=list(personality.access.allowed_faiss_indexes or []),
    )


def _build_fallback_agent_config(personality) -> AgentConfig | None:
    """Build an AgentConfig using the personality's fallback_model.

    Returns ``None`` when no fallback_model is configured.
    """
    fallback = personality.fallback_model
    if fallback is None:
        return None

    from app.models.pipeline import ProviderConfig as _PC

    provider_config = _PC(
        provider_type=fallback.provider_type,
        model_id=fallback.model_id,
        inference_profile_id=fallback.inference_profile_id,
        endpoint=fallback.endpoint,
        api_key=fallback.api_key,
        region=fallback.region,
        temperature=fallback.temperature,
        max_tokens=fallback.max_tokens,
    )
    system_prompt = personality.combined_system_prompt()
    return AgentConfig(
        name=f"chat-{personality.id}-fallback",
        model=f"{provider_config.provider_type}/{provider_config.model_id}",
        provider_config=provider_config,
        description=system_prompt,
        system_prompt=system_prompt,
        tools=list(personality.access.allowed_tools),
        faiss_indexes=list(personality.access.allowed_faiss_indexes or []),
    )


def _build_agent_prompt(messages: list[dict[str, str]]) -> str:
    """Build the prompt for a Strands agent from the message list.

    If retrieval context was injected as a system message at the start,
    it is prepended to the user's message so the agent sees it.
    """
    parts: list[str] = []
    if messages and messages[0].get("role") == "system":
        parts.append(messages[0]["content"])
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m["content"]
            break
    parts.append(user_msg)
    return "\n\n".join(parts) if len(parts) > 1 else user_msg


def _try_create_strands_agent(
    *,
    personality,
    invocation_state: dict[str, Any],
) -> ChatAgent:
    """Attempt to create a real strands.Agent; fall back to default."""
    try:
        class _StrandsWrapper:
            def __init__(self) -> None:
                agent_config = _build_chat_agent_config(personality)
                # Use ToolRegistry for agent tool selection — Requirement 8.3
                permitted_tools = _tool_registry.get_tools_for_personality(
                    personality.access.allowed_tools
                )
                self._agent = AgentFactory(ModelFactory()).create_agent(
                    agent_config, permitted_tools=permitted_tools
                )
                self._invocation_state = invocation_state

            async def respond(self, messages: list[dict[str, str]]) -> str:
                prompt = _build_agent_prompt(messages)
                result = self._agent(prompt, invocation_state=self._invocation_state)
                return str(result)

        return _StrandsWrapper()
    except Exception:
        return _DefaultChatAgent()


def _try_create_fallback_agent(
    *,
    personality,
    invocation_state: dict[str, Any],
) -> ChatAgent | None:
    """Attempt to create a fallback strands.Agent from the personality's fallback_model.

    Returns ``None`` when no fallback_model is configured or creation fails.
    """
    fallback_config = _build_fallback_agent_config(personality)
    if fallback_config is None:
        return None
    try:
        class _FallbackStrandsWrapper:
            def __init__(self) -> None:
                # Use ToolRegistry for fallback agent tool selection — Requirement 8.3
                permitted_tools = _tool_registry.get_tools_for_personality(
                    personality.access.allowed_tools
                )
                self._agent = AgentFactory(ModelFactory()).create_agent(
                    fallback_config, permitted_tools=permitted_tools
                )
                self._invocation_state = invocation_state

            async def respond(self, messages: list[dict[str, str]]) -> str:
                prompt = _build_agent_prompt(messages)
                result = self._agent(prompt, invocation_state=self._invocation_state)
                return str(result)

        return _FallbackStrandsWrapper()
    except Exception:
        logger.warning(
            "Failed to create fallback agent for personality '%s'",
            personality.id,
        )
        return None


_chat_agent_override: ChatAgent | None = None


def get_chat_agent() -> ChatAgent:
    """Return the chat agent override if set, else a default agent."""
    global _chat_agent_override
    return _chat_agent_override or _DefaultChatAgent()


def set_chat_agent(agent: ChatAgent | None) -> None:
    """Override the chat agent (useful for testing)."""
    global _chat_agent_override
    _chat_agent_override = agent


@router.get("/api/chat/provider")
async def get_chat_provider_status(user: UserContext = Depends(get_current_user)) -> dict:
    _ = user
    return _get_chat_provider_service().get_status().to_dict()


@router.post("/api/chat/provider/sign-in")
async def sign_in_chat_provider(user: UserContext = Depends(get_current_user)) -> dict:
    _ = user
    try:
        return _get_chat_provider_service().sign_in().to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/api/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str) -> None:
    """Handle bidirectional chat over WebSocket.

    The client sends JSON messages with ``{"type": "message", "content": "..."}``.
    The server responds with ``chat_token`` events (streaming) followed by a
    final ``chat_response`` event containing the full agent reply.

    Conversation history is persisted via :class:`MemoryManager` so that
    sessions survive reconnections.  On reconnect the stored history
    (which may include a condensed summary) is restored into the
    in-memory context.
    """
    await websocket.accept()

    mm = get_memory_manager()

    # Restore persisted history on (re)connect  — Requirements 1.2, 1.11
    context = _get_or_create_context(session_id)
    if not context.messages:
        restored = await mm.restore_history(session_id)
        if restored:
            for msg in restored:
                context.messages.append(
                    ChatMessage(role=msg["role"], content=msg["content"])
                )
            logger.info(
                "Restored %d messages for session %s", len(restored), session_id
            )

    store = _get_personality_store()

    try:
        while True:
            data: dict[str, Any] = await websocket.receive_json()

            msg_type = data.get("type")
            content = data.get("content", "")
            personality_id = data.get("personality_id")

            if msg_type != "message":
                await websocket.send_json(
                    {"type": "error", "content": f"Unknown message type: {msg_type}", "session_id": session_id}
                )
                continue

            # --- Personality switching — Requirements 10.1–10.5 ---
            if isinstance(personality_id, str) and personality_id and personality_id != context.personality_id:
                new_personality = store.get(personality_id)
                if new_personality is None:
                    # Req 10.4: requested personality not found — send error, keep current
                    await websocket.send_json(
                        {
                            "type": "error",
                            "content": f"Personality '{personality_id}' not found",
                            "session_id": session_id,
                        }
                    )
                else:
                    # Req 10.3: preserve conversation history (do NOT clear messages)
                    # Req 10.2: reinitialize agent with new personality's config
                    old_personality_id = context.personality_id
                    context.personality_id = personality_id

                    access_state = new_personality.access.to_invocation_state(store.base_dir)
                    invocation_state = {**access_state, "personality_id": new_personality.id}

                    context.agent = _try_create_strands_agent(
                        personality=new_personality,
                        invocation_state=invocation_state,
                    )
                    context.fallback_agent = _try_create_fallback_agent(
                        personality=new_personality,
                        invocation_state=invocation_state,
                    )
                    context.retrieval_router = _build_retrieval_router(new_personality, base_dir=store.base_dir)
                    context.escalation_detector = EscalationDetector()
                    context.system_prompt = _environment_injector.inject(
                        new_personality.combined_system_prompt(),
                        new_personality.env_data_sources,
                        store.base_dir,
                    )

                    # Req 10.5: send metadata event indicating personality change
                    await websocket.send_json(
                        {
                            "type": "personality_changed",
                            "personality_id": personality_id,
                            "session_id": session_id,
                        }
                    )
                    logger.info(
                        "Switched personality from '%s' to '%s' for session %s (preserved %d messages)",
                        old_personality_id,
                        personality_id,
                        session_id,
                        len(context.messages),
                    )

            if context.agent is None:
                override = get_chat_agent()
                if not isinstance(override, _DefaultChatAgent):
                    context.agent = override
                else:
                    provider_status = _get_chat_provider_service().get_status()
                    if provider_status.requires_sign_in:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "content": provider_status.message or "Provider sign-in is required before chatting.",
                                "session_id": session_id,
                            }
                        )
                        continue

                    personality = store.get(context.personality_id) or store.get("default")
                    if personality is None:
                        personality = store.list()[0] if store.list() else None

                    if personality is None:
                        context.agent = _DefaultChatAgent()
                    else:
                        access_state = personality.access.to_invocation_state(store.base_dir)
                        invocation_state = {**access_state, "personality_id": personality.id}
                        context.agent = _try_create_strands_agent(
                            personality=personality,
                            invocation_state=invocation_state,
                        )
                        # Inject environment data into system prompt — Requirements 7.1, 7.3
                        enhanced_prompt = _environment_injector.inject(
                            personality.combined_system_prompt(),
                            personality.env_data_sources,
                            store.base_dir,
                        )
                        context.system_prompt = enhanced_prompt
                        context.retrieval_router = _build_retrieval_router(personality, base_dir=store.base_dir)
                        logger.info(
                            "Retrieval router for personality '%s': %s (base_dir=%s)",
                            personality.id,
                            "created" if context.retrieval_router else "None (no backends)",
                            store.base_dir,
                        )
                        context.escalation_detector = EscalationDetector()
                        context.fallback_agent = _try_create_fallback_agent(
                            personality=personality,
                            invocation_state=invocation_state,
                        )

            # Record user message in context
            context.messages.append(ChatMessage(role="user", content=content))

            # Persist user message before responding — Requirement 1.1
            await mm.persist_message(session_id, "user", content)

            # Build messages list for the agent
            agent_messages = [{"role": m.role, "content": m.content} for m in context.messages]

            # Query retrieval router and inject context — Requirements 5.1, 5.3, 5.6
            if context.retrieval_router is not None:
                logger.warning("DEBUG: Querying retrieval router for session %s with: %s", session_id, content[:100])
                try:
                    retrieval_results = await context.retrieval_router.query(content)
                    logger.warning("DEBUG: Retrieval returned %d results for session %s", len(retrieval_results), session_id)
                    if retrieval_results and context.system_prompt:
                        enhanced_prompt = context.retrieval_router.inject_context(
                            retrieval_results, context.system_prompt
                        )
                        # Prepend the enhanced system prompt as a system message
                        agent_messages = [
                            {"role": "system", "content": enhanced_prompt}
                        ] + agent_messages
                except Exception as exc:
                    logger.warning(
                        "Retrieval failed for session %s: %s", session_id, exc
                    )

            # --- Escalation evaluation — Requirements 6.1, 6.2, 6.3 ---
            # Skip escalation when using a test agent override (no fallback
            # agent available in test mode).
            fallback_used = False
            use_fallback = False

            if context.escalation_detector is not None and context.fallback_agent is not None:
                conversation_depth = len(
                    [m for m in context.messages if m.role == "user"]
                )
                decision = context.escalation_detector.evaluate(
                    content, conversation_depth
                )
                if decision.should_escalate:
                    logger.info(
                        "Escalation triggered for session %s: %s",
                        session_id,
                        decision.reason,
                    )
                    use_fallback = True

            # --- Agent invocation with fallback retry — Requirements 6.4, 6.5, 6.7 ---
            response_text: str | None = None
            primary_error: Exception | None = None

            chosen_agent = context.fallback_agent if use_fallback else context.agent

            try:
                response_text = await chosen_agent.respond(agent_messages)
                if use_fallback:
                    fallback_used = True
            except Exception as exc:
                primary_error = exc

            # If primary agent failed or returned empty, retry with fallback — Req 6.4
            if (
                not use_fallback
                and context.fallback_agent is not None
                and (primary_error is not None or not response_text)
            ):
                if primary_error is not None:
                    logger.warning(
                        "Primary model failed for session %s: %s; retrying with fallback",
                        session_id,
                        primary_error,
                    )
                else:
                    logger.warning(
                        "Primary model returned empty response for session %s; retrying with fallback",
                        session_id,
                    )
                try:
                    response_text = await context.fallback_agent.respond(agent_messages)
                    fallback_used = True
                    primary_error = None  # fallback succeeded
                except Exception as fallback_exc:
                    # Both models failed — Requirement 6.5
                    details = f"primary: {primary_error or 'empty response'}, fallback: {fallback_exc}"
                    await websocket.send_json(
                        {
                            "type": "error",
                            "content": f"Both primary and fallback models failed: {details}",
                            "session_id": session_id,
                        }
                    )
                    continue

            # If we still have an error (no fallback available), send error
            if primary_error is not None:
                await websocket.send_json(
                    {"type": "error", "content": str(primary_error), "session_id": session_id}
                )
                continue

            # Guard against None/empty after all attempts
            if not response_text:
                response_text = ""

            # Stream tokens (split response into words for token-by-token delivery)
            tokens = response_text.split(" ")
            for i, token in enumerate(tokens):
                partial = token if i == 0 else " " + token
                await websocket.send_json(
                    {"type": "chat_token", "content": partial, "session_id": session_id}
                )

            # Send final complete response — Requirement 6.7: include fallback_used flag
            chat_response_event: dict[str, Any] = {
                "type": "chat_response",
                "content": response_text,
                "session_id": session_id,
            }
            if fallback_used:
                chat_response_event["fallback_used"] = True

            await websocket.send_json(chat_response_event)

            # Record assistant message in context
            context.messages.append(ChatMessage(role="assistant", content=response_text))

            # Persist assistant message and maybe condense — Requirements 1.1, 1.6
            await mm.persist_message(session_id, "assistant", response_text)
            await mm.maybe_condense(session_id)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
