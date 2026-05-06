"""Agent tools as Strands @tool decorated functions.

Provides: read_file, write_file, python_repl, shell, query_faiss.
Each tool is registered in ALL_TOOLS for use by AgentFactory.
ToolRegistry provides Strands SDK tool discovery and runtime registration.

Requirements: 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Built-in tool registry for AgentFactory (backward compatibility).
# ---------------------------------------------------------------------------
_BUILTIN_TOOLS: dict[str, object] = {
    "read": read_file,
    "write": write_file,
    "python_repl": python_repl,
    "shell": shell,
    "query_faiss": query_faiss,
}


class ToolRegistry:
    """Extended tool registry with Strands SDK discovery and runtime registration.

    Discovers tools from the ``strands_tools`` package at init, supports
    runtime custom tool registration, and filters tools by personality
    access controls.

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
    """

    def __init__(self) -> None:
        self._tools: dict[str, object] = dict(_BUILTIN_TOOLS)
        self._custom_tools: dict[str, object] = {}
        self.discover_strands_tools()

    def discover_strands_tools(self) -> list[str]:
        """Discover all tools from the ``strands_tools`` package.

        Iterates over sub-modules of ``strands_tools``, imports each one,
        and registers the tool callable found inside.  Uses try/except per
        module so that platform-specific or dependency-heavy tools that
        fail to import are silently skipped (with a logged warning).

        Returns the list of newly discovered tool names.
        """
        discovered: list[str] = []
        try:
            import strands_tools  # noqa: F811
        except ImportError:
            logger.info("strands_tools package not installed; skipping discovery")
            return discovered

        for _importer, module_name, _ispkg in pkgutil.iter_modules(
            strands_tools.__path__
        ):
            # Skip internal / utility modules.
            if module_name.startswith("_") or module_name == "utils":
                continue
            try:
                mod = importlib.import_module(f"strands_tools.{module_name}")
            except Exception:
                logger.warning(
                    "Failed to import strands_tools.%s; skipping", module_name
                )
                continue

            # Determine the tool name.  Prefer TOOL_SPEC["name"] if present,
            # otherwise fall back to the module name itself.
            tool_name: str | None = None
            tool_obj: object | None = None

            tool_spec = getattr(mod, "TOOL_SPEC", None)
            if isinstance(tool_spec, dict) and "name" in tool_spec:
                tool_name = tool_spec["name"]

            # Look for a callable with the same name as the module (common
            # pattern in strands_tools).
            candidate = getattr(mod, module_name, None)
            if callable(candidate):
                tool_obj = candidate
                if tool_name is None:
                    tool_name = module_name

            if tool_name is not None and tool_obj is not None:
                # Don't overwrite built-in tools that we defined above.
                if tool_name not in _BUILTIN_TOOLS:
                    self._tools[tool_name] = tool_obj
                    discovered.append(tool_name)

        logger.info("Discovered %d strands_tools: %s", len(discovered), discovered)
        return discovered

    # ------------------------------------------------------------------
    # Runtime custom tool registration
    # ------------------------------------------------------------------

    def register_custom_tool(self, name: str, tool: object) -> None:
        """Register a user-provided tool at runtime.

        The tool becomes available to all personalities whose
        ``allowed_tools`` list includes *name*.
        """
        self._custom_tools[name] = tool

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_tools_for_personality(self, allowed_tools: list[str]) -> list[object]:
        """Return tool objects for the intersection of registered tools and *allowed_tools*.

        Both built-in/discovered tools (``_tools``) and custom tools
        (``_custom_tools``) are considered.
        """
        all_registered = {**self._tools, **self._custom_tools}
        return [
            all_registered[name]
            for name in allowed_tools
            if name in all_registered
        ]

    def get_all_tool_names(self) -> list[str]:
        """Return a sorted list of all registered tool names (built-in + custom)."""
        return sorted(set(self._tools) | set(self._custom_tools))


# ---------------------------------------------------------------------------
# Module-level backward-compatible registries.
# ---------------------------------------------------------------------------
# ALL_TOOLS is kept as a plain dict so existing code that does
# ``ALL_TOOLS["read"]`` or ``for name in ALL_TOOLS`` continues to work.
ALL_TOOLS: dict[str, object] = _BUILTIN_TOOLS
