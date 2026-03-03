"""Unit tests for ExecutionLogger."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.models.encryption import EncryptionConfig
from app.models.execution import ExecutionStep, SessionLog
from app.models.files import IngestedFile
from app.models.pipeline import AgentConfig, OutputConfig, PipelineConfig, ProviderConfig
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.encryption_service import EncryptionService
from app.services.execution_logger import ExecutionLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Path, log_key: str = "") -> Settings:
    return Settings(
        log_dir=str(tmp_path / "logs"),
        encryption_key_log=log_key,
    )


def _make_logger(tmp_path: Path, log_key: str = "") -> ExecutionLogger:
    settings = _make_settings(tmp_path, log_key)
    return ExecutionLogger(settings=settings)


def _sample_step(step_number: int = 1, agent_id: str = "agent-1") -> ExecutionStep:
    return ExecutionStep(
        step_number=step_number,
        agent_id=agent_id,
        agent_name=f"Agent {agent_id}",
        status="completed",
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        input_data={"text": "hello"},
        prompts_sent=["Summarize this"],
        llm_responses=["Summary: hello"],
        llm_provider="bedrock",
        llm_model="claude-3-sonnet",
        decisions=["proceed"],
        output_data={"summary": "hello"},
        error=None,
    )


def _sample_config() -> PipelineConfig:
    return PipelineConfig(
        name="test-pipeline",
        agents=[
            AgentConfig(
                name="agent-1",
                model="bedrock/claude-3-sonnet",
                provider_config=ProviderConfig(provider_type="bedrock", model_id="claude-3-sonnet"),
                description="Test agent",
                tools=["read"],
            )
        ],
        output=OutputConfig(template="default", formats=["pdf"]),
    )


def _sample_ingested_file(session_id: str = "sess-1") -> IngestedFile:
    return IngestedFile(
        id="file-1",
        original_name="doc.txt",
        format="txt",
        size_bytes=5,
        content=b"hello",
        was_encrypted=False,
        session_id=session_id,
    )


def _sample_rendered_doc(session_id: str = "sess-1") -> RenderedDocument:
    return RenderedDocument(
        id="doc-1",
        session_id=session_id,
        template_id="tmpl-1",
        format="pdf",
        content=b"pdf-bytes",
        metadata=DocumentMetadata(
            author="tester",
            date=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            version="1.0",
            classification="internal",
        ),
        validation_result=[],
    )


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_log_session_start_creates_file(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [_sample_ingested_file("s1")], _sample_config())

        path = tmp_path / "logs" / "s1.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["session_id"] == "s1"
        assert data["user_id"] == "user-1"
        assert len(data["input_files"]) == 1
        assert data["completed_at"] is None

    @pytest.mark.asyncio
    async def test_log_session_end_records_outputs(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())
        await lgr.log_session_end("s1", [_sample_rendered_doc("s1")])

        data = json.loads((tmp_path / "logs" / "s1.json").read_text())
        assert data["completed_at"] is not None
        assert len(data["output_documents"]) == 1
        assert data["output_documents"][0]["id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [_sample_ingested_file("s1")], _sample_config())
        await lgr.log_step("s1", _sample_step(1, "agent-1"))
        await lgr.log_step("s1", _sample_step(2, "agent-2"))
        await lgr.log_session_end("s1", [_sample_rendered_doc("s1")])

        session_log = await lgr.get_session_log("s1")
        assert isinstance(session_log, SessionLog)
        assert session_log.session_id == "s1"
        assert session_log.user_id == "user-1"
        assert len(session_log.steps) == 2
        assert len(session_log.input_files) == 1
        assert len(session_log.output_documents) == 1
        assert session_log.completed_at is not None


# ---------------------------------------------------------------------------
# Step logging
# ---------------------------------------------------------------------------

class TestStepLogging:
    @pytest.mark.asyncio
    async def test_log_step_records_all_fields(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        step = _sample_step()
        await lgr.log_step("s1", step)

        data = json.loads((tmp_path / "logs" / "s1.json").read_text())
        recorded = data["steps"][0]
        assert recorded["step_number"] == 1
        assert recorded["agent_id"] == "agent-1"
        assert recorded["agent_name"] == "Agent agent-1"
        assert recorded["status"] == "completed"
        assert recorded["timestamp"] == "2025-01-15T10:30:00+00:00"
        assert recorded["input_data"] == {"text": "hello"}
        assert recorded["prompts_sent"] == ["Summarize this"]
        assert recorded["llm_responses"] == ["Summary: hello"]
        assert recorded["llm_provider"] == "bedrock"
        assert recorded["llm_model"] == "claude-3-sonnet"
        assert recorded["decisions"] == ["proceed"]
        assert recorded["output_data"] == {"summary": "hello"}
        assert recorded["error"] is None

    @pytest.mark.asyncio
    async def test_log_step_with_error(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        step = ExecutionStep(
            step_number=1,
            agent_id="agent-1",
            agent_name="Agent 1",
            status="failed",
            timestamp=datetime.now(timezone.utc),
            input_data={},
            prompts_sent=[],
            llm_responses=[],
            llm_provider="openai",
            llm_model="gpt-4",
            decisions=[],
            output_data={},
            error="LLM timeout",
        )
        await lgr.log_step("s1", step)

        data = json.loads((tmp_path / "logs" / "s1.json").read_text())
        assert data["steps"][0]["error"] == "LLM timeout"
        assert data["steps"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_multiple_steps_appended(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        for i in range(5):
            await lgr.log_step("s1", _sample_step(i, f"agent-{i}"))

        data = json.loads((tmp_path / "logs" / "s1.json").read_text())
        assert len(data["steps"]) == 5


# ---------------------------------------------------------------------------
# Timestamp with timezone
# ---------------------------------------------------------------------------

class TestTimestamps:
    @pytest.mark.asyncio
    async def test_timestamps_have_timezone(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())
        await lgr.log_step("s1", _sample_step())

        data = json.loads((tmp_path / "logs" / "s1.json").read_text())
        # created_at should have timezone info
        created = datetime.fromisoformat(data["created_at"])
        assert created.tzinfo is not None

        # step timestamp should have timezone info
        step_ts = datetime.fromisoformat(data["steps"][0]["timestamp"])
        assert step_ts.tzinfo is not None


# ---------------------------------------------------------------------------
# JSON validity
# ---------------------------------------------------------------------------

class TestJSONValidity:
    @pytest.mark.asyncio
    async def test_session_file_is_valid_json(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [_sample_ingested_file("s1")], _sample_config())
        await lgr.log_step("s1", _sample_step())
        await lgr.log_session_end("s1", [_sample_rendered_doc("s1")])

        raw = (tmp_path / "logs" / "s1.json").read_text()
        parsed = json.loads(raw)  # Should not raise
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# get_session_log round-trip
# ---------------------------------------------------------------------------

class TestGetSessionLog:
    @pytest.mark.asyncio
    async def test_round_trip_preserves_data(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        inp = _sample_ingested_file("s1")
        out = _sample_rendered_doc("s1")
        config = _sample_config()

        await lgr.log_session_start("s1", "user-1", [inp], config)
        await lgr.log_step("s1", _sample_step())
        await lgr.log_session_end("s1", [out])

        log = await lgr.get_session_log("s1")
        assert log.session_id == "s1"
        assert log.user_id == "user-1"
        assert log.pipeline_config.name == "test-pipeline"
        assert len(log.steps) == 1
        assert log.steps[0].agent_id == "agent-1"
        assert log.steps[0].llm_provider == "bedrock"
        assert log.steps[0].llm_model == "claude-3-sonnet"
        assert len(log.input_files) == 1
        assert log.input_files[0].content == b"hello"
        assert len(log.output_documents) == 1
        assert log.output_documents[0].content == b"pdf-bytes"

    @pytest.mark.asyncio
    async def test_empty_session_returns_defaults(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        # No file exists — should return an empty-ish SessionLog
        log = await lgr.get_session_log("nonexistent")
        assert log.session_id == ""
        assert log.steps == []


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_returns_all_sessions(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())
        await lgr.log_session_start("s2", "user-2", [], _sample_config())

        sessions = await lgr.list_sessions()
        assert len(sessions) == 2
        ids = {s["session_id"] for s in sessions}
        assert ids == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_list_with_user_filter(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())
        await lgr.log_session_start("s2", "user-2", [], _sample_config())

        sessions = await lgr.list_sessions({"user_id": "user-1"})
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_list_empty_dir(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        sessions = await lgr.list_sessions()
        assert sessions == []


# ---------------------------------------------------------------------------
# Encryption at rest
# ---------------------------------------------------------------------------

class TestEncryptionAtRest:
    @pytest.mark.asyncio
    async def test_encrypted_log_is_not_readable_json(self, tmp_path: Path):
        key = Fernet.generate_key().decode("utf-8")
        lgr = _make_logger(tmp_path, log_key=key)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        raw = (tmp_path / "logs" / "s1.json").read_bytes()
        # Encrypted content should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)

    @pytest.mark.asyncio
    async def test_encrypted_log_round_trip(self, tmp_path: Path):
        key = Fernet.generate_key().decode("utf-8")
        lgr = _make_logger(tmp_path, log_key=key)

        await lgr.log_session_start("s1", "user-1", [_sample_ingested_file("s1")], _sample_config())
        await lgr.log_step("s1", _sample_step())
        await lgr.log_session_end("s1", [_sample_rendered_doc("s1")])

        log = await lgr.get_session_log("s1")
        assert log.session_id == "s1"
        assert log.user_id == "user-1"
        assert len(log.steps) == 1
        assert len(log.input_files) == 1
        assert len(log.output_documents) == 1

    @pytest.mark.asyncio
    async def test_unencrypted_log_is_readable_json(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        raw = (tmp_path / "logs" / "s1.json").read_text()
        data = json.loads(raw)
        assert data["session_id"] == "s1"


# ---------------------------------------------------------------------------
# Input files and output documents
# ---------------------------------------------------------------------------

class TestInputOutputRecording:
    @pytest.mark.asyncio
    async def test_input_files_recorded(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        files = [
            _sample_ingested_file("s1"),
            IngestedFile(
                id="file-2",
                original_name="report.pdf",
                format="pdf",
                size_bytes=100,
                content=b"\x00\x01\x02",
                was_encrypted=True,
                session_id="s1",
            ),
        ]
        await lgr.log_session_start("s1", "user-1", files, _sample_config())

        log = await lgr.get_session_log("s1")
        assert len(log.input_files) == 2
        assert log.input_files[0].original_name == "doc.txt"
        assert log.input_files[1].original_name == "report.pdf"
        assert log.input_files[1].content == b"\x00\x01\x02"

    @pytest.mark.asyncio
    async def test_output_documents_recorded(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())
        await lgr.log_session_end("s1", [_sample_rendered_doc("s1")])

        log = await lgr.get_session_log("s1")
        assert len(log.output_documents) == 1
        doc = log.output_documents[0]
        assert doc.metadata.author == "tester"
        assert doc.metadata.classification == "internal"


# ---------------------------------------------------------------------------
# User identity and LLM provider/model per step
# ---------------------------------------------------------------------------

class TestAuditFields:
    @pytest.mark.asyncio
    async def test_user_identity_recorded(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "auditor@corp.com", [], _sample_config())

        log = await lgr.get_session_log("s1")
        assert log.user_id == "auditor@corp.com"

    @pytest.mark.asyncio
    async def test_llm_provider_model_per_step(self, tmp_path: Path):
        lgr = _make_logger(tmp_path)
        await lgr.log_session_start("s1", "user-1", [], _sample_config())

        step1 = _sample_step(1, "agent-1")
        step2 = ExecutionStep(
            step_number=2,
            agent_id="agent-2",
            agent_name="Agent 2",
            status="completed",
            timestamp=datetime.now(timezone.utc),
            input_data={},
            prompts_sent=[],
            llm_responses=[],
            llm_provider="openai_compatible",
            llm_model="gpt-4o",
            decisions=[],
            output_data={},
            error=None,
        )
        await lgr.log_step("s1", step1)
        await lgr.log_step("s1", step2)

        log = await lgr.get_session_log("s1")
        assert log.steps[0].llm_provider == "bedrock"
        assert log.steps[0].llm_model == "claude-3-sonnet"
        assert log.steps[1].llm_provider == "openai_compatible"
        assert log.steps[1].llm_model == "gpt-4o"
