from __future__ import annotations

from app.engine.tools import python_repl, read_file, shell, write_file

CHAT_TOOLS: dict[str, object] = {
    "read": read_file,
    "write": write_file,
    "python_repl": python_repl,
    "shell": shell,
}
