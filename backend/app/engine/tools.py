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


@tool
def read_file(path: str) -> str:
    """Read file contents from the local file system.

    Args:
        path: Path to the file to read
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file on the local file system.

    Args:
        path: Path to the file to write
        content: Content to write to the file
    """
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
