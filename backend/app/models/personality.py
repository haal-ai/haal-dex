from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersonalityAccess:
    allowed_tools: list[str] = field(default_factory=list)
    allowed_read_roots: list[str] | None = None
    allowed_write_roots: list[str] | None = None
    allowed_faiss_indexes: list[int] | None = None

    def to_invocation_state(self, base_dir: Path) -> dict[str, Any]:
        def _resolve_many(values: list[str] | None) -> list[str] | None:
            if values is None:
                return None
            resolved: list[str] = []
            for v in values:
                p = Path(v)
                if not p.is_absolute():
                    p = (base_dir / p).resolve()
                resolved.append(str(p))
            return resolved

        return {
            "allowed_read_roots": _resolve_many(self.allowed_read_roots),
            "allowed_write_roots": _resolve_many(self.allowed_write_roots),
            "allowed_faiss_indexes": self.allowed_faiss_indexes,
        }


@dataclass
class Personality:
    id: str
    name: str
    description: str
    system_prompt: str
    instructions: str = ""
    access: PersonalityAccess = field(default_factory=PersonalityAccess)

    def combined_system_prompt(self) -> str:
        if self.instructions.strip():
            return f"{self.system_prompt.strip()}\n\n{self.instructions.strip()}"
        return self.system_prompt.strip()
