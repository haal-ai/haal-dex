"""Unit tests for backend/app/engine/tools.py

Tests: read_file, write_file, python_repl, shell, query_faiss, ALL_TOOLS registry.
Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import os
import platform
import tempfile
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.engine.tools import (
    ALL_TOOLS,
    python_repl,
    query_faiss,
    read_file,
    shell,
    write_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(tool_fn, **kwargs):
    """Call a tool function, stripping any Strands wrapper if present."""
    # Strands @tool wraps the function; the underlying callable is still usable directly.
    fn = getattr(tool_fn, "__wrapped__", tool_fn)
    return fn(**kwargs)


def _make_tool_context(faiss_manager=None):
    """Build a minimal object that mimics Strands ToolContext.invocation_state."""
    state = {"faiss_manager": faiss_manager} if faiss_manager is not None else {}
    return SimpleNamespace(invocation_state=state)


def _make_tool_context_with_state(state: dict):
    return SimpleNamespace(invocation_state=state)


# ---------------------------------------------------------------------------
# ALL_TOOLS registry
# ---------------------------------------------------------------------------

class TestAllToolsRegistry:
    """Verify the ALL_TOOLS dict contains all expected tool names."""

    def test_registry_contains_expected_keys(self):
        expected = {"read", "write", "python_repl", "shell", "query_faiss"}
        assert set(ALL_TOOLS.keys()) == expected

    def test_registry_values_are_callable(self):
        for name, tool_fn in ALL_TOOLS.items():
            fn = getattr(tool_fn, "__wrapped__", tool_fn)
            assert callable(fn), f"ALL_TOOLS['{name}'] is not callable"


# ---------------------------------------------------------------------------
# read_file  (Requirement 6.1)
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_reads_existing_file(self, tmp_path):
        p = tmp_path / "hello.txt"
        p.write_text("hello world", encoding="utf-8")
        result = _call(read_file, path=str(p))
        assert result == "hello world"

    def test_reads_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        result = _call(read_file, path=str(p))
        assert result == ""

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _call(read_file, path=str(tmp_path / "nope.txt"))

    def test_denies_read_when_outside_allowed_roots(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()
        p = denied / "secret.txt"
        p.write_text("no", encoding="utf-8")

        ctx = _make_tool_context_with_state({"allowed_read_roots": [str(allowed)]})
        fn = getattr(read_file, "__wrapped__", read_file)
        result = fn(path=str(p), tool_context=ctx)
        assert "access denied" in result

    def test_allows_read_when_within_allowed_roots(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        p = allowed / "ok.txt"
        p.write_text("yes", encoding="utf-8")

        ctx = _make_tool_context_with_state({"allowed_read_roots": [str(allowed)]})
        fn = getattr(read_file, "__wrapped__", read_file)
        result = fn(path=str(p), tool_context=ctx)
        assert result == "yes"


# ---------------------------------------------------------------------------
# write_file  (Requirement 6.2)
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_writes_content(self, tmp_path):
        p = tmp_path / "out.txt"
        result = _call(write_file, path=str(p), content="data")
        assert "4 bytes" in result
        assert p.read_text(encoding="utf-8") == "data"

    def test_creates_parent_directories(self, tmp_path):
        p = tmp_path / "sub" / "dir" / "file.txt"
        _call(write_file, path=str(p), content="nested")
        assert p.read_text(encoding="utf-8") == "nested"

    def test_overwrites_existing_file(self, tmp_path):
        p = tmp_path / "overwrite.txt"
        p.write_text("old", encoding="utf-8")
        _call(write_file, path=str(p), content="new")
        assert p.read_text(encoding="utf-8") == "new"

    def test_denies_write_when_outside_allowed_roots(self, tmp_path):
        allowed = tmp_path / "allowed"
        denied = tmp_path / "denied"
        allowed.mkdir()
        denied.mkdir()
        p = denied / "blocked.txt"

        ctx = _make_tool_context_with_state({"allowed_write_roots": [str(allowed)]})
        fn = getattr(write_file, "__wrapped__", write_file)
        result = fn(path=str(p), content="x", tool_context=ctx)
        assert "access denied" in result
        assert not p.exists()

    def test_allows_write_when_within_allowed_roots(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        p = allowed / "ok.txt"

        ctx = _make_tool_context_with_state({"allowed_write_roots": [str(allowed)]})
        fn = getattr(write_file, "__wrapped__", write_file)
        result = fn(path=str(p), content="x", tool_context=ctx)
        assert "Written" in result
        assert p.read_text(encoding="utf-8") == "x"


# ---------------------------------------------------------------------------
# python_repl  (Requirement 6.3 — cross-platform)
# ---------------------------------------------------------------------------

class TestPythonRepl:
    def test_simple_expression(self):
        result = _call(python_repl, code="print(2 + 3)")
        assert "5" in result

    def test_multiline_code(self):
        code = "for i in range(3):\n    print(i)"
        result = _call(python_repl, code=code)
        assert "0" in result and "1" in result and "2" in result

    def test_syntax_error_returns_error(self):
        result = _call(python_repl, code="def")
        assert "Error" in result or "SyntaxError" in result

    def test_no_output_returns_marker(self):
        result = _call(python_repl, code="x = 1")
        assert result == "(no output)"

    def test_import_works(self):
        result = _call(python_repl, code="import os; print(os.name)")
        assert result.strip() in ("nt", "posix")


# ---------------------------------------------------------------------------
# shell  (Requirement 6.4 — Bash on Linux, PowerShell on Windows)
# ---------------------------------------------------------------------------

class TestShell:
    def test_echo_command(self):
        if platform.system() == "Windows":
            result = _call(shell, command="Write-Output 'hello'")
        else:
            result = _call(shell, command="echo hello")
        assert "hello" in result

    def test_invalid_command_returns_error(self):
        result = _call(shell, command="nonexistent_command_xyz_12345")
        assert "Error" in result or "not" in result.lower()

    def test_platform_detection(self):
        """Verify the tool uses the correct shell for the current platform."""
        if platform.system() == "Windows":
            # PowerShell-specific: $PSVersionTable exists
            result = _call(shell, command="echo $PSVersionTable.PSVersion")
            # Should not error out on PowerShell
            assert "Error" not in result or "PSVersion" in result
        else:
            # Bash-specific: $BASH_VERSION exists
            result = _call(shell, command="echo $BASH_VERSION")
            assert "Error" not in result


# ---------------------------------------------------------------------------
# query_faiss  (Requirement 5.3 via tool — accesses FAISS manager)
# ---------------------------------------------------------------------------

class TestQueryFaiss:
    def test_returns_error_when_no_context(self):
        ctx = _make_tool_context(faiss_manager=None)
        fn = getattr(query_faiss, "__wrapped__", query_faiss)
        result = fn(query="test", index_id=0, tool_context=ctx)
        assert "Error" in result

    def test_returns_error_when_no_faiss_manager(self):
        ctx = SimpleNamespace(invocation_state={})
        fn = getattr(query_faiss, "__wrapped__", query_faiss)
        result = fn(query="test", index_id=0, tool_context=ctx)
        assert "FAISS manager not available" in result

    def test_delegates_to_faiss_manager(self):
        mock_manager = MagicMock()
        mock_manager.query.return_value = [
            {"fragment": "doc1", "score": 0.95},
            {"fragment": "doc2", "score": 0.80},
        ]
        ctx = _make_tool_context(faiss_manager=mock_manager)
        fn = getattr(query_faiss, "__wrapped__", query_faiss)
        result = fn(query="search term", index_id=1, tool_context=ctx)
        mock_manager.query.assert_called_once_with(1, "search term")
        assert "doc1" in result
        assert "0.95" in result

    def test_handles_faiss_manager_exception(self):
        mock_manager = MagicMock()
        mock_manager.query.side_effect = RuntimeError("index not loaded")
        ctx = _make_tool_context(faiss_manager=mock_manager)
        fn = getattr(query_faiss, "__wrapped__", query_faiss)
        result = fn(query="q", index_id=2, tool_context=ctx)
        assert "Error querying FAISS index 2" in result
        assert "index not loaded" in result


# ---------------------------------------------------------------------------
# read_file + write_file round trip  (Requirements 6.1, 6.2)
# ---------------------------------------------------------------------------

class TestReadWriteRoundTrip:
    def test_write_then_read_returns_original(self, tmp_path):
        p = tmp_path / "roundtrip.txt"
        content = "round-trip content with special chars: é à ü"
        _call(write_file, path=str(p), content=content)
        result = _call(read_file, path=str(p))
        assert result == content
