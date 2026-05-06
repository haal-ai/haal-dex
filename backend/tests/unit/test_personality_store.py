"""Unit tests for PersonalityStore extensions (Task 1.2).

Tests cover:
- serialize / deserialize round-trip
- deserialize with unknown fields (ignored)
- deserialize with malformed JSON (descriptive error)
- _migrate_legacy_access mapping
- _parse_personality with new fields and backward-compatible defaults
- fallback_model defaults to primary_model when omitted
- validate_backends reachability checks
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.models.personality import (
    ModelConfig,
    Personality,
    PersonalityAccess,
    RetrievalACLEntry,
    RetrievalBackendConfig,
)
from app.services.personality_store import PersonalityStore


@pytest.fixture()
def store(tmp_path: Path) -> PersonalityStore:
    store_path = tmp_path / "config" / "personalities.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("{}", encoding="utf-8")
    return PersonalityStore(store_path)


def _make_personality(**overrides) -> Personality:
    defaults = dict(
        id="test-1",
        name="Test",
        description="A test personality",
        system_prompt="You are helpful.",
        instructions="",
        access=PersonalityAccess(),
        retrieval_backends=[],
        primary_model=None,
        fallback_model=None,
        env_data_sources=[],
    )
    defaults.update(overrides)
    return Personality(**defaults)


# ------------------------------------------------------------------
# serialize / deserialize
# ------------------------------------------------------------------


class TestSerialize:
    def test_produces_valid_json(self, store: PersonalityStore) -> None:
        p = _make_personality()
        result = store.serialize(p)
        data = json.loads(result)
        assert data["id"] == "test-1"
        assert data["name"] == "Test"

    def test_handles_nested_dataclasses(self, store: PersonalityStore) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    db_path="./data.db",
                    fts_table="docs",
                )
            ],
            primary_model=ModelConfig(model_id="claude-3"),
        )
        result = store.serialize(p)
        data = json.loads(result)
        assert data["retrieval_backends"][0]["backend_type"] == "sqlite_bm25"
        assert data["primary_model"]["model_id"] == "claude-3"


class TestDeserialize:
    def test_round_trip_minimal(self, store: PersonalityStore) -> None:
        p = _make_personality()
        json_str = store.serialize(p)
        restored = store.deserialize(json_str)
        assert restored.id == p.id
        assert restored.name == p.name
        assert restored.description == p.description
        assert restored.system_prompt == p.system_prompt

    def test_round_trip_with_all_fields(self, store: PersonalityStore) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    db_path="./data.db",
                    fts_table="docs",
                    top_k=10,
                    name="my-sqlite",
                )
            ],
            primary_model=ModelConfig(
                provider_type="bedrock",
                model_id="claude-3",
                temperature=0.5,
            ),
            fallback_model=ModelConfig(
                provider_type="bedrock",
                model_id="claude-sonnet",
                temperature=0.3,
            ),
            env_data_sources=["./readme.md", "$MY_VAR"],
            access=PersonalityAccess(
                allowed_tools=["read", "write"],
                allowed_retrieval_indexes=[
                    RetrievalACLEntry(
                        backend_type="sqlite_bm25", index_name="./data.db"
                    )
                ],
            ),
        )
        json_str = store.serialize(p)
        restored = store.deserialize(json_str)

        assert restored.retrieval_backends[0].backend_type == "sqlite_bm25"
        assert restored.retrieval_backends[0].db_path == "./data.db"
        assert restored.retrieval_backends[0].top_k == 10
        assert restored.primary_model is not None
        assert restored.primary_model.model_id == "claude-3"
        assert restored.fallback_model is not None
        assert restored.fallback_model.model_id == "claude-sonnet"
        assert restored.env_data_sources == ["./readme.md", "$MY_VAR"]
        assert restored.access.allowed_retrieval_indexes is not None
        assert len(restored.access.allowed_retrieval_indexes) == 1

    def test_unknown_fields_ignored(self, store: PersonalityStore) -> None:
        data = {
            "id": "p1",
            "name": "P1",
            "description": "desc",
            "system_prompt": "prompt",
            "unknown_top_level": 42,
            "access": {"allowed_tools": [], "unknown_access_field": True},
        }
        json_str = json.dumps(data)
        p = store.deserialize(json_str)
        assert p.id == "p1"
        assert p.name == "P1"

    def test_malformed_json_raises_descriptive_error(
        self, store: PersonalityStore
    ) -> None:
        with pytest.raises(ValueError, match="Malformed personality JSON"):
            store.deserialize("{bad json")

    def test_malformed_json_includes_location(
        self, store: PersonalityStore
    ) -> None:
        with pytest.raises(ValueError, match=r"line \d+.*column \d+"):
            store.deserialize("{bad json")

    def test_non_object_json_raises(self, store: PersonalityStore) -> None:
        with pytest.raises(ValueError, match="expected a JSON object"):
            store.deserialize('"just a string"')


# ------------------------------------------------------------------
# _migrate_legacy_access
# ------------------------------------------------------------------


class TestMigrateLegacyAccess:
    def test_maps_faiss_indexes_to_retrieval_indexes(
        self, store: PersonalityStore
    ) -> None:
        data = {
            "id": "p1",
            "access": {
                "allowed_faiss_indexes": [0, 1, 2],
            },
        }
        result = store._migrate_legacy_access(data)
        acl = result["access"]["allowed_retrieval_indexes"]
        assert len(acl) == 3
        assert all(e["backend_type"] == "faiss_embedding" for e in acl)
        assert [e["index_name"] for e in acl] == ["0", "1", "2"]

    def test_does_not_overwrite_existing_retrieval_indexes(
        self, store: PersonalityStore
    ) -> None:
        data = {
            "id": "p1",
            "access": {
                "allowed_faiss_indexes": [0],
                "allowed_retrieval_indexes": [
                    {"backend_type": "sqlite_bm25", "index_name": "db.sqlite"}
                ],
            },
        }
        result = store._migrate_legacy_access(data)
        acl = result["access"]["allowed_retrieval_indexes"]
        assert len(acl) == 1
        assert acl[0]["backend_type"] == "sqlite_bm25"

    def test_no_access_key_returns_unchanged(
        self, store: PersonalityStore
    ) -> None:
        data = {"id": "p1"}
        result = store._migrate_legacy_access(data)
        assert result == data

    def test_no_faiss_indexes_returns_unchanged(
        self, store: PersonalityStore
    ) -> None:
        data = {"id": "p1", "access": {"allowed_tools": ["read"]}}
        result = store._migrate_legacy_access(data)
        assert "allowed_retrieval_indexes" not in result["access"]


# ------------------------------------------------------------------
# _parse_personality with new fields
# ------------------------------------------------------------------


class TestParsePersonalityNewFields:
    def test_backward_compatible_defaults(self, store: PersonalityStore) -> None:
        """Legacy personality data (no new fields) still parses correctly."""
        data = {
            "id": "legacy",
            "name": "Legacy",
            "description": "Old style",
            "system_prompt": "Hello",
        }
        p = store._parse_personality(data)
        assert p.retrieval_backends == []
        assert p.primary_model is None
        assert p.fallback_model is None
        assert p.env_data_sources == []

    def test_parses_retrieval_backends(self, store: PersonalityStore) -> None:
        data = {
            "id": "p1",
            "retrieval_backends": [
                {
                    "backend_type": "sqlite_bm25",
                    "db_path": "./data.db",
                    "fts_table": "docs",
                    "top_k": 10,
                }
            ],
        }
        p = store._parse_personality(data)
        assert len(p.retrieval_backends) == 1
        rb = p.retrieval_backends[0]
        assert rb.backend_type == "sqlite_bm25"
        assert rb.db_path == "./data.db"
        assert rb.top_k == 10

    def test_parses_model_configs(self, store: PersonalityStore) -> None:
        data = {
            "id": "p1",
            "primary_model": {"model_id": "haiku", "temperature": 0.5},
            "fallback_model": {"model_id": "sonnet", "max_tokens": 4096},
        }
        p = store._parse_personality(data)
        assert p.primary_model is not None
        assert p.primary_model.model_id == "haiku"
        assert p.primary_model.temperature == 0.5
        assert p.fallback_model is not None
        assert p.fallback_model.model_id == "sonnet"
        assert p.fallback_model.max_tokens == 4096

    def test_parses_env_data_sources(self, store: PersonalityStore) -> None:
        data = {
            "id": "p1",
            "env_data_sources": ["./readme.md", "$API_KEY"],
        }
        p = store._parse_personality(data)
        assert p.env_data_sources == ["./readme.md", "$API_KEY"]


# ------------------------------------------------------------------
# Fallback model defaults to primary
# ------------------------------------------------------------------


class TestFallbackModelDefault:
    def test_fallback_defaults_to_primary_when_omitted(
        self, store: PersonalityStore
    ) -> None:
        data = {
            "id": "p1",
            "primary_model": {
                "provider_type": "bedrock",
                "model_id": "haiku",
                "temperature": 0.7,
            },
        }
        p = store._parse_personality(data)
        assert p.fallback_model is not None
        assert p.fallback_model.model_id == "haiku"
        assert p.fallback_model.provider_type == "bedrock"
        assert p.fallback_model.temperature == 0.7

    def test_fallback_is_independent_copy(
        self, store: PersonalityStore
    ) -> None:
        """Changing the fallback should not affect the primary."""
        data = {
            "id": "p1",
            "primary_model": {"model_id": "haiku"},
        }
        p = store._parse_personality(data)
        assert p.primary_model is not p.fallback_model

    def test_no_primary_means_no_fallback(
        self, store: PersonalityStore
    ) -> None:
        data = {"id": "p1"}
        p = store._parse_personality(data)
        assert p.primary_model is None
        assert p.fallback_model is None

    def test_explicit_fallback_not_overridden(
        self, store: PersonalityStore
    ) -> None:
        data = {
            "id": "p1",
            "primary_model": {"model_id": "haiku"},
            "fallback_model": {"model_id": "sonnet"},
        }
        p = store._parse_personality(data)
        assert p.fallback_model is not None
        assert p.fallback_model.model_id == "sonnet"


# ------------------------------------------------------------------
# validate_backends
# ------------------------------------------------------------------


class TestValidateBackends:
    def test_empty_backends_returns_no_errors(
        self, store: PersonalityStore
    ) -> None:
        p = _make_personality()
        assert store.validate_backends(p) == []

    def test_sqlite_missing_db_path(self, store: PersonalityStore) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(backend_type="sqlite_bm25")
            ]
        )
        errors = store.validate_backends(p)
        assert len(errors) == 1
        assert "No db_path" in errors[0]

    def test_sqlite_db_not_found(
        self, store: PersonalityStore, tmp_path: Path
    ) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25",
                    db_path=str(tmp_path / "nonexistent.db"),
                )
            ]
        )
        errors = store.validate_backends(p)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_sqlite_db_exists_no_error(
        self, store: PersonalityStore, tmp_path: Path
    ) -> None:
        db = tmp_path / "data.db"
        db.write_text("")
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="sqlite_bm25", db_path=str(db)
                )
            ]
        )
        errors = store.validate_backends(p)
        assert errors == []

    def test_faiss_index_not_found(
        self, store: PersonalityStore, tmp_path: Path
    ) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="faiss_embedding",
                    index_path=str(tmp_path / "missing.index"),
                )
            ]
        )
        errors = store.validate_backends(p)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_faiss_index_exists_no_error(
        self, store: PersonalityStore, tmp_path: Path
    ) -> None:
        idx = tmp_path / "my.index"
        idx.write_text("")
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(
                    backend_type="faiss_embedding", index_path=str(idx)
                )
            ]
        )
        errors = store.validate_backends(p)
        assert errors == []

    def test_unknown_backend_type(self, store: PersonalityStore) -> None:
        p = _make_personality(
            retrieval_backends=[
                RetrievalBackendConfig(backend_type="unknown_type")
            ]
        )
        errors = store.validate_backends(p)
        assert len(errors) == 1
        assert "Unknown backend type" in errors[0]


# ------------------------------------------------------------------
# Integration: load from file with new fields
# ------------------------------------------------------------------


class TestLoadWithNewFields:
    def test_load_personality_with_all_new_fields(
        self, tmp_path: Path
    ) -> None:
        config = {
            "personalities": {
                "expert": {
                    "name": "Expert",
                    "description": "An expert",
                    "system_prompt": "You are an expert.",
                    "retrieval_backends": [
                        {
                            "backend_type": "sqlite_bm25",
                            "db_path": "./data.db",
                            "fts_table": "docs",
                        }
                    ],
                    "primary_model": {"model_id": "haiku"},
                    "env_data_sources": ["./readme.md"],
                    "access": {
                        "allowed_tools": ["read"],
                        "allowed_faiss_indexes": [0, 1],
                    },
                }
            }
        }
        store_path = tmp_path / "config" / "personalities.json"
        store_path.parent.mkdir(parents=True)
        store_path.write_text(json.dumps(config), encoding="utf-8")

        ps = PersonalityStore(store_path)
        personalities = ps.load()
        p = personalities["expert"]

        assert p.name == "Expert"
        assert len(p.retrieval_backends) == 1
        assert p.retrieval_backends[0].backend_type == "sqlite_bm25"
        assert p.primary_model is not None
        assert p.primary_model.model_id == "haiku"
        # fallback defaults to primary
        assert p.fallback_model is not None
        assert p.fallback_model.model_id == "haiku"
        assert p.env_data_sources == ["./readme.md"]
        # legacy migration
        assert p.access.allowed_retrieval_indexes is not None
        assert len(p.access.allowed_retrieval_indexes) == 2
        assert all(
            e.backend_type == "faiss_embedding"
            for e in p.access.allowed_retrieval_indexes
        )
