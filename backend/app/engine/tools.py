"""Agent tools as Strands @tool decorated functions.

Provides: read_file, write_file, python_repl, shell, query_faiss.
Each tool is registered in ALL_TOOLS for use by AgentFactory.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

# Try importing Strands SDK @tool decorator; fall back to identity decorator.
try:
    from strands import tool
    _STRANDS_AVAILABLE = True
except ImportError:
    _STRANDS_AVAILABLE = False

    def tool(fn=None, **kwargs):  # type: ignore[misc]
        """Fallback identity decorator when strands is not installed."""
        if fn is not None:
            return fn
        return lambda f: f


def _is_path_allowed(path: str, allowed_roots: list[str] | None) -> bool:
    if allowed_roots is None:
        return True

    try:
        target = Path(path).resolve()
    except Exception:
        return False

    for root in allowed_roots:
        try:
            root_path = Path(root).resolve()
            common = os.path.commonpath([str(target), str(root_path)])
            if common == str(root_path):
                return True
        except Exception:
            continue

    return False


def _get_invocation_state(tool_context) -> dict:
    if tool_context is None:
        return {}
    state = getattr(tool_context, "invocation_state", None)
    return state if isinstance(state, dict) else {}


@tool(context=True)
def read_file(path: str, tool_context=None) -> str:
    """Read file contents from the local file system.

    Args:
        path: Path to the file to read
    """
    state = _get_invocation_state(tool_context)
    allowed_roots = state.get("allowed_read_roots")
    if isinstance(allowed_roots, list) and not _is_path_allowed(path, allowed_roots):
        return f"Error: access denied to read path: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@tool(context=True)
def write_file(path: str, content: str, tool_context=None) -> str:
    """Write content to a file on the local file system.

    Args:
        path: Path to the file to write
        content: Content to write to the file
    """
    state = _get_invocation_state(tool_context)
    allowed_roots = state.get("allowed_write_roots")
    if isinstance(allowed_roots, list) and not _is_path_allowed(path, allowed_roots):
        return f"Error: access denied to write path: {path}"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written {len(content)} bytes to {path}"


@tool
def python_repl(code: str) -> str:
    """Execute Python code and return the result. Works on both Windows and Linux.

    Uses subprocess to execute in an isolated environment.

    Args:
        code: Python code to execute
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.returncode != 0:
            output = output + result.stderr if output else result.stderr
            return f"Error (exit {result.returncode}):\n{output}"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: execution timed out after 30 seconds"
    except Exception as exc:
        return f"Error: {exc}"


@tool
def shell(command: str) -> str:
    """Execute a shell command. Uses Bash on Linux and PowerShell on Windows.

    Args:
        command: Shell command to execute
    """
    is_windows = platform.system() == "Windows"

    if is_windows:
        shell_cmd = ["powershell", "-NoProfile", "-Command", command]
    else:
        shell_cmd = ["bash", "-c", command]

    try:
        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.returncode != 0:
            output = output + result.stderr if output else result.stderr
            return f"Error (exit {result.returncode}):\n{output}"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: execution timed out after 30 seconds"
    except Exception as exc:
        return f"Error: {exc}"


# query_faiss uses context=True so Strands injects tool_context automatically.
if _STRANDS_AVAILABLE:
    @tool(context=True)
    def query_faiss(query: str, index_id: int, tool_context) -> str:
        """Query a FAISS index for similar documents.

        Args:
            query: The search query text
            index_id: The FAISS index to query (0-3)
        """
        allowed_indexes = tool_context.invocation_state.get("allowed_faiss_indexes")
        if isinstance(allowed_indexes, list) and index_id not in allowed_indexes:
            return f"Error: access denied to FAISS index {index_id}"
        faiss_manager = tool_context.invocation_state.get("faiss_manager")
        if faiss_manager is None:
            return "Error: FAISS manager not available"
        try:
            results = faiss_manager.query(index_id, query)
            return str(results)
        except Exception as exc:
            return f"Error querying FAISS index {index_id}: {exc}"
else:
    # Fallback when strands is not installed (testing / dev).
    def query_faiss(query: str, index_id: int, tool_context=None) -> str:  # type: ignore[misc]
        """Query a FAISS index for similar documents.

        Args:
            query: The search query text
            index_id: The FAISS index to query (0-3)
        """
        if tool_context is None:
            return "Error: FAISS manager not available"
        allowed_indexes = tool_context.invocation_state.get("allowed_faiss_indexes")
        if isinstance(allowed_indexes, list) and index_id not in allowed_indexes:
            return f"Error: access denied to FAISS index {index_id}"
        faiss_manager = tool_context.invocation_state.get("faiss_manager")
        if faiss_manager is None:
            return "Error: FAISS manager not available"
        try:
            results = faiss_manager.query(index_id, query)
            return str(results)
        except Exception as exc:
            return f"Error querying FAISS index {index_id}: {exc}"


# Tool registry for AgentFactory to select from.
ALL_TOOLS: dict[str, object] = {
    "read": read_file,
    "write": write_file,
    "python_repl": python_repl,
    "shell": shell,
    "query_faiss": query_faiss,
}
