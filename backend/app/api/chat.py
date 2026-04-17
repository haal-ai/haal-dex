"""Chat WebSocket endpoint.

Provides:
- WS /api/ws/chat/{session_id} — bidirectional chat via WebSocket

Each session maintains a conversation history (list of messages).
When a message is received it is sent to a strands.Agent (or a mock
agent when the SDK is not installed) and the response is streamed
back token by token.

Protocol:
  Client sends:  {"type": "message", "content": "user message"}
  Server sends:  {"type": "chat_token",    "content": "partial", "session_id": "..."}
  Server sends:  {"type": "chat_response", "content": "full response", "session_id": "..."}

Requirements: 2.1, 2.3, 2.4, 17.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.engine.agent_factory import AgentFactory
from app.engine.model_factory import ModelFactory
from app.engine.chat_tools import CHAT_TOOLS
from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.pipeline import AgentConfig
from app.services.personality_store import PersonalityStore
from app.services.chat_provider_service import ChatProviderService

router = APIRouter(tags=["chat"])

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
                self._agent = AgentFactory(ModelFactory()).create_agent(agent_config)
                self._invocation_state = invocation_state

            async def respond(self, messages: list[dict[str, str]]) -> str:
                prompt = messages[-1]["content"] if messages else ""
                result = self._agent(prompt, invocation_state=self._invocation_state)
                return str(result)

        return _StrandsWrapper()
    except Exception:
        return _DefaultChatAgent()


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
    """
    await websocket.accept()

    context = _get_or_create_context(session_id)
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

            if isinstance(personality_id, str) and personality_id and personality_id != context.personality_id:
                context.personality_id = personality_id
                context.messages.clear()
                context.agent = None

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

            # Record user message in context
            context.messages.append(ChatMessage(role="user", content=content))

            # Build messages list for the agent
            agent_messages = [{"role": m.role, "content": m.content} for m in context.messages]

            try:
                response_text = await context.agent.respond(agent_messages)
            except Exception as exc:
                await websocket.send_json(
                    {"type": "error", "content": str(exc), "session_id": session_id}
                )
                continue

            # Stream tokens (split response into words for token-by-token delivery)
            tokens = response_text.split(" ")
            for i, token in enumerate(tokens):
                partial = token if i == 0 else " " + token
                await websocket.send_json(
                    {"type": "chat_token", "content": partial, "session_id": session_id}
                )

            # Send final complete response
            await websocket.send_json(
                {"type": "chat_response", "content": response_text, "session_id": session_id}
            )

            # Record assistant message in context
            context.messages.append(ChatMessage(role="assistant", content=response_text))

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
