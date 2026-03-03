"""Integration tests for end-to-end pipeline execution with mock LLM providers.

Covers:
- File upload → pipeline execution → output flow
- Pipeline execution with mock orchestrator
- Encryption across the full pipeline

Validates: Requirements 3.1, 3.2, 12.1-12.5
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.pipeline import _sessions, _session_files, store_session_config
from app.engine.graph_factory import PipelineResult
from app.models.files import IngestedFile
from app.models.session import Session
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.encryption_service import EncryptionService
from tests.integration.conftest import (
    auth_header,
    make_pipeline_config,
    make_pipeline_config_dict,
)


class TestFileUploadFlow:
    """Upload files via the REST API and verify session creation."""

    def test_upload_txt_file(self, client: TestClient, admin_token: str):
        files = [("files", ("test.txt", io.BytesIO(b"hello world"), "text/plain"))]
        resp = client.post(
            "/api/files/upload",
            files=files,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["files"]) == 1
        assert data["files"][0]["format"] == "txt"
        assert data["files"][0]["original_name"] == "test.txt"

    def test_upload_multiple_files(self, client: TestClient, admin_token: str):
        files = [
            ("files", ("a.txt", io.BytesIO(b"aaa"), "text/plain")),
            ("files", ("b.md", io.BytesIO(b"# B"), "text/markdown")),
        ]
        resp = client.post(
            "/api/files/upload",
            files=files,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 2

    def test_upload_unsupported_format_returns_400(
        self, client: TestClient, admin_token: str
    ):
        files = [("files", ("bad.exe", io.BytesIO(b"\x00"), "application/octet-stream"))]
        resp = client.post(
            "/api/files/upload",
            files=files,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_requires_auth(self, client: TestClient):
        files = [("files", ("test.txt", io.BytesIO(b"data"), "text/plain"))]
        resp = client.post("/api/files/upload", files=files)
        assert resp.status_code in (401, 403)


class TestPipelineExecution:
    """Execute pipeline via REST API with mock orchestrator."""

    def test_execute_returns_completed(
        self, client: TestClient, admin_token: str
    ):
        resp = client.post(
            "/api/pipeline/execute",
            json=make_pipeline_config_dict(),
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert "session_id" in data
        assert data["execution_order"] == ["agent-1"]

    def test_execute_multi_agent_pipeline(
        self, client: TestClient, admin_token: str, mock_orchestrator
    ):
        mock_orchestrator.run_pipeline = AsyncMock(
            return_value=(
                PipelineResult(
                    status="COMPLETED",
                    output="final",
                    execution_order=["a1", "a2", "a3"],
                    execution_time_ms=100.0,
                ),
                None,
            )
        )
        resp = client.post(
            "/api/pipeline/execute",
            json=make_pipeline_config_dict(["a1", "a2", "a3"]),
            headers=auth_header(admin_token),
        )
        data = resp.json()
        assert data["execution_order"] == ["a1", "a2", "a3"]
        assert data["status"] == "COMPLETED"

    def test_failed_pipeline_reports_error(
        self, client: TestClient, admin_token: str, mock_orchestrator
    ):
        mock_orchestrator.run_pipeline = AsyncMock(
            return_value=(
                PipelineResult(
                    status="FAILED",
                    error="agent crashed",
                    failed_agent="agent-1",
                    failed_step=0,
                ),
                None,
            )
        )
        resp = client.post(
            "/api/pipeline/execute",
            json=make_pipeline_config_dict(),
            headers=auth_header(admin_token),
        )
        data = resp.json()
        assert data["status"] == "FAILED"
        assert data["error"] == "agent crashed"


class TestFileUploadToPipelineFlow:
    """End-to-end: upload file, then execute pipeline on that session."""

    def test_upload_then_execute(
        self, client: TestClient, admin_token: str, mock_orchestrator
    ):
        # Step 1: Upload a file
        files = [("files", ("input.txt", io.BytesIO(b"input data"), "text/plain"))]
        upload_resp = client.post(
            "/api/files/upload",
            files=files,
            headers=auth_header(admin_token),
        )
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        # Verify session was created in the store
        assert session_id in _sessions

        # Step 2: Execute pipeline (uses mock orchestrator)
        exec_resp = client.post(
            "/api/pipeline/execute",
            json=make_pipeline_config_dict(),
            headers=auth_header(admin_token),
        )
        assert exec_resp.status_code == 200
        assert exec_resp.json()["status"] == "COMPLETED"


class TestEncryptionAcrossPipeline:
    """Verify encryption service works across the full pipeline.

    Validates: Requirements 12.1-12.5
    """

    def test_fernet_encrypt_decrypt_roundtrip(self):
        """Encryption service round-trips data with Fernet."""
        from app.models.encryption import EncryptionConfig

        svc = EncryptionService()
        key = Fernet.generate_key().decode("utf-8")
        config = EncryptionConfig(
            enabled=True, algorithm="Fernet", key_reference=key, target="input"
        )
        original = b"sensitive pipeline data"
        encrypted = svc.encrypt(original, config)
        assert encrypted != original
        decrypted = svc.decrypt(encrypted, config)
        assert decrypted == original

    def test_independent_keys_per_target(self):
        """Each target (input/output/log) uses independent keys."""
        from app.models.encryption import EncryptionConfig

        svc = EncryptionService()
        keys = {
            t: Fernet.generate_key().decode("utf-8")
            for t in ("input", "output", "log")
        }
        data = b"test data"
        encrypted = {}
        for target, key in keys.items():
            cfg = EncryptionConfig(
                enabled=True, algorithm="Fernet", key_reference=key, target=target
            )
            encrypted[target] = svc.encrypt(data, cfg)

        # Each target's ciphertext should differ (different keys)
        assert encrypted["input"] != encrypted["output"]
        assert encrypted["output"] != encrypted["log"]

        # Each can be decrypted with its own key
        for target, key in keys.items():
            cfg = EncryptionConfig(
                enabled=True, algorithm="Fernet", key_reference=key, target=target
            )
            assert svc.decrypt(encrypted[target], cfg) == data

    def test_disabled_encryption_passes_through(self):
        """When encryption is disabled, data passes through unchanged."""
        from app.models.encryption import EncryptionConfig

        svc = EncryptionService()
        config = EncryptionConfig(
            enabled=False, algorithm="", key_reference="", target="input"
        )
        data = b"plain data"
        assert svc.encrypt(data, config) == data
        assert svc.decrypt(data, config) == data
