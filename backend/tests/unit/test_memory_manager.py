"""Unit tests for MemoryManager."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.services.memory_manager import MemoryManager


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


class TestPersistAndRestore:
    """Tests for persist_message and restore_history."""

    @pytest.mark.asyncio
    async def test_persist_then_restore_single_message(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("s1", "user", "hello")
        msgs = await mm.restore_history("s1")
        assert msgs == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_persist_then_restore_multiple_messages(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("s1", "user", "hello")
        await mm.persist_message("s1", "assistant", "hi there")
        await mm.persist_message("s1", "user", "how are you?")
        msgs = await mm.restore_history("s1")
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "hello"}
        assert msgs[1] == {"role": "assistant", "content": "hi there"}
        assert msgs[2] == {"role": "user", "content": "how are you?"}

    @pytest.mark.asyncio
    async def test_restore_empty_session(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        msgs = await mm.restore_history("nonexistent")
        assert msgs == []

    @pytest.mark.asyncio
    async def test_separate_sessions_are_isolated(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("s1", "user", "session one")
        await mm.persist_message("s2", "user", "session two")
        assert (await mm.restore_history("s1")) == [{"role": "user", "content": "session one"}]
        assert (await mm.restore_history("s2")) == [{"role": "user", "content": "session two"}]

    @pytest.mark.asyncio
    async def test_persist_updates_metadata(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("s1", "user", "hello")
        path = storage_dir / "s1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["metadata"]["total_turns"] == 1
        assert data["metadata"]["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_json_file_created_at_correct_path(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("my-session", "user", "test")
        assert (storage_dir / "my-session.json").exists()


class TestMaybeCondense:
    """Tests for maybe_condense."""

    @pytest.mark.asyncio
    async def test_no_condense_below_turn_threshold(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir, condense_every_n_turns=10)
        for i in range(5):
            await mm.persist_message("s1", "user", f"msg {i}")
        result = await mm.maybe_condense("s1")
        assert result is False

    @pytest.mark.asyncio
    async def test_condense_at_turn_threshold(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir, condense_every_n_turns=5, preserve_recent=2)
        for i in range(6):
            role = "user" if i % 2 == 0 else "assistant"
            await mm.persist_message("s1", role, f"message {i}")
        result = await mm.maybe_condense("s1")
        assert result is True
        msgs = await mm.restore_history("s1")
        # 1 summary + 2 recent = 3
        assert len(msgs) == 3
        assert msgs[0]["role"] == "summary"
        assert msgs[1] == {"role": "user", "content": "message 4"}
        assert msgs[2] == {"role": "assistant", "content": "message 5"}

    @pytest.mark.asyncio
    async def test_condense_at_token_threshold(self, storage_dir: Path) -> None:
        mm = MemoryManager(
            storage_dir,
            condense_every_n_turns=1000,  # high turn threshold
            token_threshold=50,  # low token threshold
            preserve_recent=1,
        )
        # Each message ~100 chars -> ~25 tokens, 3 messages -> ~75 tokens > 50
        await mm.persist_message("s1", "user", "a" * 100)
        await mm.persist_message("s1", "assistant", "b" * 100)
        await mm.persist_message("s1", "user", "c" * 100)
        result = await mm.maybe_condense("s1")
        assert result is True
        msgs = await mm.restore_history("s1")
        assert len(msgs) == 2  # 1 summary + 1 recent
        assert msgs[0]["role"] == "summary"

    @pytest.mark.asyncio
    async def test_condense_preserves_recent_messages(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir, condense_every_n_turns=4, preserve_recent=3)
        for i in range(5):
            await mm.persist_message("s1", "user", f"msg-{i}")
        await mm.maybe_condense("s1")
        msgs = await mm.restore_history("s1")
        # Recent 3 preserved
        recent = msgs[1:]
        assert len(recent) == 3
        assert recent[0]["content"] == "msg-2"
        assert recent[1]["content"] == "msg-3"
        assert recent[2]["content"] == "msg-4"

    @pytest.mark.asyncio
    async def test_condense_summary_contains_older_content(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir, condense_every_n_turns=3, preserve_recent=1)
        await mm.persist_message("s1", "user", "important fact alpha")
        await mm.persist_message("s1", "assistant", "noted beta")
        await mm.persist_message("s1", "user", "latest message")
        await mm.maybe_condense("s1")
        msgs = await mm.restore_history("s1")
        summary = msgs[0]["content"]
        assert "important fact alpha" in summary
        assert "noted beta" in summary

    @pytest.mark.asyncio
    async def test_condense_updates_metadata(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir, condense_every_n_turns=3, preserve_recent=1)
        for i in range(4):
            await mm.persist_message("s1", "user", f"msg {i}")
        await mm.maybe_condense("s1")
        path = storage_dir / "s1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["metadata"]["condensation_count"] == 1
        assert data["metadata"]["last_condensed_at"] is not None

    @pytest.mark.asyncio
    async def test_condense_nonexistent_session_returns_false(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        result = await mm.maybe_condense("nonexistent")
        assert result is False


class TestCreateConversationManager:
    """Tests for create_conversation_manager."""

    def test_returns_conversation_manager_or_none(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        result = mm.create_conversation_manager()
        # Either returns a SummarizingConversationManager or None
        # depending on whether strands SDK is installed
        if result is not None:
            assert hasattr(result, "apply_management")


class TestStorageFormat:
    """Tests for the JSON storage format."""

    @pytest.mark.asyncio
    async def test_session_file_has_expected_structure(self, storage_dir: Path) -> None:
        mm = MemoryManager(storage_dir)
        await mm.persist_message("s1", "user", "hello")
        path = storage_dir / "s1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "session_id" in data
        assert "messages" in data
        assert "metadata" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_storage_dir_created_automatically(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        mm = MemoryManager(nested)
        await mm.persist_message("s1", "user", "test")
        assert nested.exists()
        assert (nested / "s1.json").exists()
