from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RetrievalBackendConfig:
    """Configuration for a single retrieval backend."""

    backend_type: str  # "sqlite_bm25" | "faiss_embedding" | "bedrock_embedding"
    # SQLite BM25 fields
    db_path: str | None = None
    fts_table: str | None = None
    ranking_algorithm: str = "bm25_okapi"  # "bm25_okapi" | "bm25f"
    column_weights: list[float] | None = None  # per-column BM25F boost weights
    # FAISS/Bedrock fields
    index_path: str | None = None
    embedding_model: str | None = None  # sentence-transformer model or Bedrock model ID
    # Common
    top_k: int = 5
    name: str = ""


@dataclass
class ModelConfig:
    """Configuration for a model provider."""

    provider_type: str = "bedrock"
    model_id: str = ""
    inference_profile_id: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    region: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass
class RetrievalACLEntry:
    """Access control entry for a retrieval backend."""

    backend_type: str  # "sqlite_bm25" | "faiss_embedding" | "bedrock_embedding"
    index_name: str  # db_path for SQLite, index name for FAISS/Bedrock


@dataclass
class PersonalityAccess:
    allowed_tools: list[str] = field(default_factory=list)
    allowed_read_roots: list[str] | None = None
    allowed_write_roots: list[str] | None = None
    allowed_faiss_indexes: list[int] | None = None  # backward compat
    allowed_retrieval_indexes: list[RetrievalACLEntry] | None = None

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
    # New fields — all have defaults for backward compatibility
    retrieval_backends: list[RetrievalBackendConfig] = field(default_factory=list)
    primary_model: ModelConfig | None = None
    fallback_model: ModelConfig | None = None
    env_data_sources: list[str] = field(default_factory=list)

    def combined_system_prompt(self) -> str:
        if self.instructions.strip():
            return f"{self.system_prompt.strip()}\n\n{self.instructions.strip()}"
        return self.system_prompt.strip()
