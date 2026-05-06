"""Conversation memory persistence and condensation.

Manages durable storage of chat messages per session and periodic
condensation of older messages into compact summaries.  When the
Strands SDK is available the ``SummarizingConversationManager`` is
used for intelligent summarisation; otherwise a simple concatenation
fallback is applied.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Strands SDK import – graceful degradation
# ---------------------------------------------------------------------------
_strands_available = False
_SummarizingConversationManager: type | None = None

try:
    from strands.agent.conversation_manager import (
        SummarizingConversationManager as _SCM,
    )

    _strands_available = True
    _SummarizingConversationManager = _SCM
except ImportError:
    logger.warning(
        "strands-agents SDK not available – "
        "MemoryManager will use file-based persistence only"
    )


def _estimate_token_count(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


class MemoryManager:
    """Manages conversation memory persistence and condensation."""

    def __init__(
        self,
        storage_dir: Path,
        condense_every_n_turns: int = 10,
        token_threshold: int = 4000,
        summary_ratio: float = 0.3,
        preserve_recent: int = 10,
    ) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._condense_every_n_turns = condense_every_n_turns
        self._token_threshold = token_threshold
        self._summary_ratio = summary_ratio
        self._preserve_recent = preserve_recent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def persist_message(
        self, session_id: str, role: str, content: str
    ) -> None:
        """Persist a message to durable storage before response is sent."""
        try:
            data = self._read_session(session_id)
            data["messages"].append({"role": role, "content": content})
            data["metadata"]["total_turns"] = len(data["messages"])
            data["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_session(session_id, data)
        except Exception:
            logger.exception("Failed to persist message for session %s", session_id)

    async def restore_history(
        self, session_id: str
    ) -> list[dict[str, str]]:
        """Restore full conversation history from durable storage."""
        try:
            data = self._read_session(session_id)
            return list(data["messages"])
        except Exception:
            logger.exception(
                "Failed to restore history for session %s – returning empty",
                session_id,
            )
            return []

    async def maybe_condense(self, session_id: str) -> bool:
        """Run condensation if turn count or token threshold exceeded.

        Returns ``True`` if condensation occurred.
        """
        try:
            data = self._read_session(session_id)
            messages: list[dict[str, str]] = data["messages"]

            if not self._should_condense(messages):
                return False

            condensed = self._condense_messages(messages)
            data["messages"] = condensed
            data["metadata"]["total_turns"] = len(condensed)
            data["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
            data["metadata"]["condensation_count"] = (
                data["metadata"].get("condensation_count", 0) + 1
            )
            data["metadata"]["last_condensed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            self._write_session(session_id, data)
            return True
        except Exception:
            logger.exception(
                "Condensation failed for session %s – original messages preserved",
                session_id,
            )
            return False

    def create_conversation_manager(self) -> Any:
        """Create a Strands ``SummarizingConversationManager`` instance.

        Returns ``None`` if the Strands SDK is unavailable.
        """
        if not _strands_available or _SummarizingConversationManager is None:
            logger.warning(
                "Strands SDK unavailable – cannot create SummarizingConversationManager"
            )
            return None

        return _SummarizingConversationManager(
            summary_ratio=self._summary_ratio,
            preserve_recent_messages=self._preserve_recent,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.json"

    def _read_session(self, session_id: str) -> dict[str, Any]:
        path = self._session_path(session_id)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return self._empty_session(session_id)

    def _write_session(self, session_id: str, data: dict[str, Any]) -> None:
        path = self._session_path(session_id)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def _empty_session(session_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "session_id": session_id,
            "personality_id": "default",
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "metadata": {
                "total_turns": 0,
                "condensation_count": 0,
                "last_condensed_at": None,
            },
        }

    def _should_condense(self, messages: list[dict[str, str]]) -> bool:
        """Check whether condensation should trigger."""
        turn_count = len(messages)
        if turn_count >= self._condense_every_n_turns:
            return True

        total_tokens = sum(
            _estimate_token_count(m.get("content", "")) for m in messages
        )
        if total_tokens >= self._token_threshold:
            return True

        return False

    def _condense_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Replace older messages with a single summary message.

        Keeps the most recent ``preserve_recent`` messages intact and
        replaces everything before them with one ``"summary"`` role
        message.
        """
        if len(messages) <= self._preserve_recent:
            # Nothing to condense – all messages are "recent"
            return list(messages)

        older = messages[: -self._preserve_recent]
        recent = messages[-self._preserve_recent :]

        summary_text = self._summarize(older)
        summary_message: dict[str, str] = {
            "role": "summary",
            "content": summary_text,
        }
        return [summary_message] + list(recent)

    def _summarize(self, messages: list[dict[str, str]]) -> str:
        """Produce a summary of the given messages.

        Uses a simple concatenation approach that preserves key facts.
        The Strands ``SummarizingConversationManager`` (if available) is
        used at the agent level for richer summarisation; this method
        provides the file-based fallback.
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content.strip():
                parts.append(f"[{role}] {content.strip()}")

        return (
            "Summary of earlier conversation:\n" + "\n".join(parts)
            if parts
            else "Summary of earlier conversation: (no content)"
        )
