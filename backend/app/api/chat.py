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
from typing import Any, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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


def _try_create_strands_agent() -> ChatAgent:
    """Attempt to create a real strands.Agent; fall back to default."""
    try:
        from strands import Agent  # type: ignore[import-untyped]

        class _StrandsWrapper:
            def __init__(self) -> None:
                self._agent = Agent(
                    system_prompt=(
                        "You are a helpful bilingual assistant (English/French). "
                        "Respond in the same language the user writes in."
                    ),
                )

            async def respond(self, messages: list[dict[str, str]]) -> str:
                prompt = messages[-1]["content"] if messages else ""
                result = self._agent(prompt)
                return str(result)

        return _StrandsWrapper()
    except Exception:
        return _DefaultChatAgent()


# Module-level agent instance (lazy-initialised on first connection).
_chat_agent: ChatAgent | None = None


def get_chat_agent() -> ChatAgent:
    """Return the module-level chat agent, creating it on first call."""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = _try_create_strands_agent()
    return _chat_agent


def set_chat_agent(agent: ChatAgent) -> None:
    """Override the chat agent (useful for testing)."""
    global _chat_agent
    _chat_agent = agent


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
    agent = get_chat_agent()

    try:
        while True:
            data: dict[str, Any] = await websocket.receive_json()

            msg_type = data.get("type")
            content = data.get("content", "")

            if msg_type != "message":
                await websocket.send_json(
                    {"type": "error", "content": f"Unknown message type: {msg_type}", "session_id": session_id}
                )
                continue

            # Record user message in context
            context.messages.append(ChatMessage(role="user", content=content))

            # Build messages list for the agent
            agent_messages = [{"role": m.role, "content": m.content} for m in context.messages]

            try:
                response_text = await agent.respond(agent_messages)
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
