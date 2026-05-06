from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from app.models.personality import (
    ModelConfig,
    Personality,
    PersonalityAccess,
    RetrievalACLEntry,
    RetrievalBackendConfig,
)

logger = logging.getLogger(__name__)


class PersonalityStore:
    def __init__(self, store_path: str | Path) -> None:
        self._store_path = Path(store_path)
        self._base_dir = self._store_path.parent.parent.resolve()
        self._cache: dict[str, Personality] | None = None

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _load_raw(self) -> dict:
        if not self._store_path.exists():
            return {"personalities": {}}
        with self._store_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def _migrate_legacy_access(self, data: dict) -> dict:
        """Map allowed_faiss_indexes to allowed_retrieval_indexes for backward compat.

        If ``allowed_faiss_indexes`` is present but ``allowed_retrieval_indexes``
        is not, create :class:`RetrievalACLEntry`-style dicts with
        ``backend_type="faiss_embedding"`` for each index.
        """
        access = data.get("access")
        if not isinstance(access, dict):
            return data

        has_legacy = access.get("allowed_faiss_indexes") is not None
        has_new = access.get("allowed_retrieval_indexes") is not None

        if has_legacy and not has_new:
            migrated: list[dict] = []
            for idx in access["allowed_faiss_indexes"]:
                migrated.append(
                    {"backend_type": "faiss_embedding", "index_name": str(idx)}
                )
            data = {**data, "access": {**access, "allowed_retrieval_indexes": migrated}}

        return data

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retrieval_backend(raw: dict) -> RetrievalBackendConfig:
        raw_weights = raw.get("column_weights")
        column_weights = (
            [float(w) for w in raw_weights] if isinstance(raw_weights, list) else None
        )
        return RetrievalBackendConfig(
            backend_type=str(raw.get("backend_type", "")),
            db_path=raw.get("db_path"),
            fts_table=raw.get("fts_table"),
            ranking_algorithm=str(raw.get("ranking_algorithm", "bm25_okapi")),
            column_weights=column_weights,
            index_path=raw.get("index_path"),
            embedding_model=raw.get("embedding_model"),
            top_k=int(raw.get("top_k", 5)),
            name=str(raw.get("name", "")),
        )

    @staticmethod
    def _parse_model_config(raw: dict | None) -> ModelConfig | None:
        if raw is None:
            return None
        return ModelConfig(
            provider_type=str(raw.get("provider_type", "bedrock")),
            model_id=str(raw.get("model_id", "")),
            inference_profile_id=raw.get("inference_profile_id"),
            endpoint=raw.get("endpoint"),
            api_key=raw.get("api_key"),
            region=raw.get("region"),
            temperature=float(raw.get("temperature", 0.7)),
            max_tokens=int(raw.get("max_tokens", 2048)),
        )

    @staticmethod
    def _parse_acl_entries(raw_list: list | None) -> list[RetrievalACLEntry] | None:
        if raw_list is None:
            return None
        return [
            RetrievalACLEntry(
                backend_type=str(entry.get("backend_type", "")),
                index_name=str(entry.get("index_name", "")),
            )
            for entry in raw_list
            if isinstance(entry, dict)
        ]

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def _parse_personality(self, data: dict) -> Personality:
        # Apply legacy migration before parsing
        data = self._migrate_legacy_access(data)

        access_data = data.get("access") or {}
        access = PersonalityAccess(
            allowed_tools=list(access_data.get("allowed_tools") or []),
            allowed_read_roots=access_data.get("allowed_read_roots"),
            allowed_write_roots=access_data.get("allowed_write_roots"),
            allowed_faiss_indexes=access_data.get("allowed_faiss_indexes"),
            allowed_retrieval_indexes=self._parse_acl_entries(
                access_data.get("allowed_retrieval_indexes")
            ),
        )

        # Parse new fields with backward-compatible defaults
        retrieval_backends = [
            self._parse_retrieval_backend(rb)
            for rb in (data.get("retrieval_backends") or [])
            if isinstance(rb, dict)
        ]

        primary_model = self._parse_model_config(data.get("primary_model"))
        fallback_model = self._parse_model_config(data.get("fallback_model"))

        # Requirement 2.9: when fallback_model is omitted, default to primary_model
        if fallback_model is None and primary_model is not None:
            fallback_model = self._parse_model_config(asdict(primary_model))

        env_data_sources = list(data.get("env_data_sources") or [])

        return Personality(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            instructions=str(data.get("instructions") or ""),
            access=access,
            retrieval_backends=retrieval_backends,
            primary_model=primary_model,
            fallback_model=fallback_model,
            env_data_sources=env_data_sources,
        )

    # ------------------------------------------------------------------
    # Serialization / deserialization
    # ------------------------------------------------------------------

    def serialize(self, personality: Personality) -> str:
        """Serialize a Personality to a JSON string."""
        return json.dumps(asdict(personality), ensure_ascii=False)

    def deserialize(self, json_str: str) -> Personality:
        """Deserialize a JSON string to a Personality.

        Unknown fields are silently ignored.  Malformed JSON raises a
        descriptive :class:`ValueError` indicating the parse failure location.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed personality JSON: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                "Malformed personality JSON: expected a JSON object at top level"
            )

        return self._parse_personality(data)

    # ------------------------------------------------------------------
    # Backend validation
    # ------------------------------------------------------------------

    def validate_backends(self, personality: Personality) -> list[str]:
        """Validate that all retrieval backend connections are reachable.

        Returns a list of error messages.  An empty list means all backends
        are valid.

        Checks performed per backend type:
        - **sqlite_bm25**: ``db_path`` file exists.
        - **faiss_embedding** / **bedrock_embedding**: ``index_path`` file exists.
        - **bedrock_embedding** (additional): Bedrock credentials are available
          (``boto3.Session`` can be created without error).
        """
        errors: list[str] = []
        for backend in personality.retrieval_backends:
            bt = backend.backend_type
            name_label = backend.name or bt

            if bt == "sqlite_bm25":
                if not backend.db_path:
                    errors.append(f"[{name_label}] No db_path configured")
                elif not Path(backend.db_path).exists():
                    errors.append(
                        f"[{name_label}] SQLite database not found: {backend.db_path}"
                    )

            elif bt in ("faiss_embedding", "bedrock_embedding"):
                if not backend.index_path:
                    errors.append(f"[{name_label}] No index_path configured")
                elif not Path(backend.index_path).exists():
                    errors.append(
                        f"[{name_label}] Index file not found: {backend.index_path}"
                    )

                if bt == "bedrock_embedding":
                    try:
                        import boto3  # noqa: F811

                        boto3.Session()
                    except Exception as exc:  # noqa: BLE001
                        errors.append(
                            f"[{name_label}] Bedrock credentials unavailable: {exc}"
                        )
            else:
                errors.append(f"[{name_label}] Unknown backend type: {bt}")

        return errors

    # ------------------------------------------------------------------
    # Store operations (unchanged)
    # ------------------------------------------------------------------

    def load(self, *, force: bool = False) -> dict[str, Personality]:
        if self._cache is not None and not force:
            return self._cache

        raw = self._load_raw()
        personalities: dict[str, Personality] = {}
        for pid, pdata in (raw.get("personalities") or {}).items():
            if isinstance(pdata, dict) and "id" not in pdata:
                pdata = {**pdata, "id": pid}
            personality = self._parse_personality(pdata)
            personalities[personality.id] = personality

        self._cache = personalities
        return personalities

    def list(self) -> list[Personality]:
        return sorted(self.load().values(), key=lambda p: p.name.lower())

    def get(self, personality_id: str) -> Personality | None:
        return self.load().get(personality_id)

    def to_public_dict(self, personality: Personality) -> dict:
        data = asdict(personality)
        data.pop("access", None)
        data["access"] = {
            "allowed_tools": list(personality.access.allowed_tools),
            "allowed_read_roots": personality.access.allowed_read_roots,
            "allowed_write_roots": personality.access.allowed_write_roots,
            "allowed_faiss_indexes": personality.access.allowed_faiss_indexes,
        }
        return data
