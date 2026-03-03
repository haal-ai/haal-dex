"""Unit tests for PipelineOrchestrator wiring.

Verifies the full flow: file upload → pipeline execution → output generation,
with ExecutionLogger, MetricsCollector, and EncryptionService integration.

Requirements: 1.1-1.5, 3.1-3.5, 7.3, 8.1-8.3, 9.1-9.4, 11.1-11.3,
              12.3-12.5, 13.1-13.3, 17.1-17.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.graph_factory import GraphFactory, PipelineResult
from app.models.encryption import EncryptionConfig
from app.models.files import IngestedFile
from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.models.session import Session
from app.models.templates import DocumentMetadata, RenderedDocument
from app.pipeline_orchestrator import PipelineOrchestrator
from app.services.encryption_service import EncryptionService
from app.services.execution_logger import ExecutionLogger
from app.services.metrics_collector import MetricsCollector
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_config() -> ProviderConfig:
    return ProviderConfig(provider_type="bedrock", model_id="claude-3-sonnet")


def _agent_config(name: str = "agent-1") -> AgentConfig:
    return AgentConfig(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=_provider_config(),
        description=f"Agent {name}",
    )


def _pipeline_config(
    agent_names: list[str] | None = None,
    template: str = "default",
) -> PipelineConfig:
    names = agent_names or ["agent-1"]
    return PipelineConfig(
        name="test-pipeline",
        agents=[_agent_config(n) for n in names],
        output=OutputConfig(template=template, formats=["pdf"]),
    )


def _ingested_file(
    session_id: str = "sess-1",
    name: str = "test.txt",
    content: bytes = b"hello world",
) -> IngestedFile:
    return IngestedFile(
        id=str(uuid.uuid4()),
        original_name=name,
        format="txt",
        size_bytes=len(content),
        content=content,
        was_encrypted=False,
        session_id=session_id,
    )


def _rendered_doc(session_id: str = "sess-1") -> RenderedDocument:
    return RenderedDocument(
        id=str(uuid.uuid4()),
        session_id=session_id,
        template_id="default",
        format="html",
        content=b"<html>output</html>",
        metadata=DocumentMetadata(
            author="user-1",
            date=datetime.now(timezone.utc),
            version="1.0",
            classification="internal",
        ),
        validation_result=[],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_graph_factory() -> MagicMock:
    factory = MagicMock(spec=GraphFactory)
    factory.execute = AsyncMock(
        return_value=PipelineResult(
            status="COMPLETED",
            output="pipeline output",
            execution_order=["agent-1"],
            execution_time_ms=42.0,
        )
    )
    factory.stream_execute = AsyncMock(
        return_value=PipelineResult(
            status="COMPLETED",
            output="streamed output",
            execution_order=["agent-1"],
            execution_time_ms=55.0,
        )
    )
    return factory


@pytest.fixture
def mock_execution_logger() -> MagicMock:
    logger = MagicMock(spec=ExecutionLogger)
    logger.log_session_start = AsyncMock()
    logger.log_session_end = AsyncMock()
    logger.log_step = AsyncMock()
    return logger


@pytest.fixture
def mock_metrics_collector() -> MagicMock:
    return MagicMock(spec=MetricsCollector)


@pytest.fixture
def mock_encryption_service() -> MagicMock:
    svc = MagicMock(spec=EncryptionService)
    svc.get_config.return_value = EncryptionConfig(
        enabled=False, algorithm="", key_reference="", target="input"
    )
    return svc


@pytest.fixture
def mock_template_registry() -> MagicMock:
    return MagicMock(spec=TemplateRegistry)


@pytest.fixture
def mock_output_generator() -> MagicMock:
    gen = MagicMock(spec=OutputGenerator)
    gen.render = AsyncMock(return_value=_rendered_doc())
    return gen


@pytest.fixture
def orchestrator(
    mock_graph_factory,
    mock_execution_logger,
    mock_metrics_collector,
    mock_output_generator,
    mock_encryption_service,
    mock_template_registry,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        graph_factory=mock_graph_factory,
        execution_logger=mock_execution_logger,
        metrics_collector=mock_metrics_collector,
        output_generator=mock_output_generator,
        encryption_service=mock_encryption_service,
        template_registry=mock_template_registry,
    )


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------

class TestCreateSession:
    def test_creates_session_with_uuid(self, orchestrator):
        config = _pipeline_config()
        session = orchestrator.create_session("user-1", config)
        assert len(session.id) == 36
        assert session.user_id == "user-1"
        assert session.pipeline_config_id == "test-pipeline"
        assert session.status == "pending"

    def test_session_has_utc_timestamp(self, orchestrator):
        session = orchestrator.create_session("user-1", _pipeline_config())
        assert session.created_at.tzinfo is not None
        assert session.completed_at is None


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_logs_session_start(
        self, orchestrator, mock_execution_logger
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        files = [_ingested_file(session.id)]

        await orchestrator.run_pipeline(session, _pipeline_config(), files)

        mock_execution_logger.log_session_start.assert_called_once()
        call_kwargs = mock_execution_logger.log_session_start.call_args.kwargs
        assert call_kwargs["session_id"] == session.id
        assert call_kwargs["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_logs_session_end(
        self, orchestrator, mock_execution_logger
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        await orchestrator.run_pipeline(session, _pipeline_config(), [])

        mock_execution_logger.log_session_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_graph_factory_execute(
        self, orchestrator, mock_graph_factory
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        await orchestrator.run_pipeline(session, _pipeline_config(), [])

        mock_graph_factory.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_pipeline_result(self, orchestrator):
        session = orchestrator.create_session("user-1", _pipeline_config())
        result, doc = await orchestrator.run_pipeline(
            session, _pipeline_config(), []
        )

        assert result.status == "COMPLETED"
        assert result.output == "pipeline output"

    @pytest.mark.asyncio
    async def test_session_status_completed(self, orchestrator):
        session = orchestrator.create_session("user-1", _pipeline_config())
        await orchestrator.run_pipeline(session, _pipeline_config(), [])

        assert session.status == "completed"
        assert session.completed_at is not None

    @pytest.mark.asyncio
    async def test_session_status_failed_on_pipeline_failure(
        self, orchestrator, mock_graph_factory
    ):
        mock_graph_factory.execute = AsyncMock(
            return_value=PipelineResult(
                status="FAILED",
                error="agent crashed",
                failed_agent="agent-1",
                failed_step=0,
            )
        )
        session = orchestrator.create_session("user-1", _pipeline_config())
        result, doc = await orchestrator.run_pipeline(
            session, _pipeline_config(), []
        )

        assert session.status == "failed"
        assert result.status == "FAILED"

    @pytest.mark.asyncio
    async def test_records_metrics_for_executed_agents(
        self, orchestrator, mock_metrics_collector
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        await orchestrator.run_pipeline(session, _pipeline_config(), [])

        mock_metrics_collector.record.assert_called()

    @pytest.mark.asyncio
    async def test_logs_execution_steps(
        self, orchestrator, mock_execution_logger
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        await orchestrator.run_pipeline(session, _pipeline_config(), [])

        # log_step called for each agent in execution_order
        assert mock_execution_logger.log_step.call_count >= 1

    @pytest.mark.asyncio
    async def test_generates_output_on_success(
        self, orchestrator, mock_output_generator, mock_template_registry
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        result, doc = await orchestrator.run_pipeline(
            session, _pipeline_config(), []
        )

        mock_output_generator.render.assert_called_once()
        assert doc is not None

    @pytest.mark.asyncio
    async def test_no_output_on_failure(
        self, orchestrator, mock_graph_factory, mock_output_generator
    ):
        mock_graph_factory.execute = AsyncMock(
            return_value=PipelineResult(status="FAILED", error="boom")
        )
        session = orchestrator.create_session("user-1", _pipeline_config())
        result, doc = await orchestrator.run_pipeline(
            session, _pipeline_config(), []
        )

        mock_output_generator.render.assert_not_called()
        assert doc is None

    @pytest.mark.asyncio
    async def test_no_output_when_template_empty(
        self, orchestrator, mock_output_generator
    ):
        config = _pipeline_config(template="")
        session = orchestrator.create_session("user-1", config)
        result, doc = await orchestrator.run_pipeline(session, config, [])

        mock_output_generator.render.assert_not_called()
        assert doc is None

    @pytest.mark.asyncio
    async def test_exception_sets_session_failed(
        self, orchestrator, mock_graph_factory, mock_execution_logger
    ):
        mock_graph_factory.execute = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        session = orchestrator.create_session("user-1", _pipeline_config())

        with pytest.raises(RuntimeError, match="unexpected"):
            await orchestrator.run_pipeline(session, _pipeline_config(), [])

        assert session.status == "failed"
        mock_execution_logger.log_session_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_decrypts_files_when_encryption_enabled(
        self, orchestrator, mock_encryption_service
    ):
        mock_encryption_service.get_config.return_value = EncryptionConfig(
            enabled=True,
            algorithm="Fernet",
            key_reference="test-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=",
            target="input",
        )
        session = orchestrator.create_session("user-1", _pipeline_config())
        files = [_ingested_file(session.id)]

        # Patch FileIngestionService at its source module
        with patch(
            "app.services.file_ingestion.FileIngestionService"
        ) as MockFIS:
            mock_fis = MockFIS.return_value
            mock_fis.decrypt_if_needed = AsyncMock(side_effect=lambda f, c: f)

            await orchestrator.run_pipeline(session, _pipeline_config(), files)

            mock_fis.decrypt_if_needed.assert_called_once()

    @pytest.mark.asyncio
    async def test_formats_file_contents_as_input(self, orchestrator, mock_graph_factory):
        session = orchestrator.create_session("user-1", _pipeline_config())
        files = [
            _ingested_file(session.id, "a.txt", b"content A"),
            _ingested_file(session.id, "b.txt", b"content B"),
        ]

        await orchestrator.run_pipeline(session, _pipeline_config(), files)

        call_kwargs = mock_graph_factory.execute.call_args.kwargs
        input_data = call_kwargs["input_data"]
        assert "a.txt" in input_data
        assert "content A" in input_data
        assert "b.txt" in input_data
        assert "content B" in input_data


# ---------------------------------------------------------------------------
# stream_pipeline
# ---------------------------------------------------------------------------

class TestStreamPipeline:
    @pytest.mark.asyncio
    async def test_calls_stream_execute(
        self, orchestrator, mock_graph_factory
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        await orchestrator.stream_pipeline(
            session, _pipeline_config(), [], ws
        )

        mock_graph_factory.stream_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_websocket_to_graph_factory(
        self, orchestrator, mock_graph_factory
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        await orchestrator.stream_pipeline(
            session, _pipeline_config(), [], ws
        )

        call_kwargs = mock_graph_factory.stream_execute.call_args.kwargs
        assert call_kwargs["websocket"] is ws

    @pytest.mark.asyncio
    async def test_logs_session_start_and_end(
        self, orchestrator, mock_execution_logger
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        await orchestrator.stream_pipeline(
            session, _pipeline_config(), [], ws
        )

        mock_execution_logger.log_session_start.assert_called_once()
        mock_execution_logger.log_session_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_metrics(
        self, orchestrator, mock_metrics_collector
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        await orchestrator.stream_pipeline(
            session, _pipeline_config(), [], ws
        )

        mock_metrics_collector.record.assert_called()

    @pytest.mark.asyncio
    async def test_generates_output_on_success(
        self, orchestrator, mock_output_generator
    ):
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        result, doc = await orchestrator.stream_pipeline(
            session, _pipeline_config(), [], ws
        )

        mock_output_generator.render.assert_called_once()
        assert doc is not None

    @pytest.mark.asyncio
    async def test_exception_sets_session_failed(
        self, orchestrator, mock_graph_factory, mock_execution_logger
    ):
        mock_graph_factory.stream_execute = AsyncMock(
            side_effect=RuntimeError("stream error")
        )
        session = orchestrator.create_session("user-1", _pipeline_config())
        ws = MagicMock()
        ws.send_json = AsyncMock()

        with pytest.raises(RuntimeError, match="stream error"):
            await orchestrator.stream_pipeline(
                session, _pipeline_config(), [], ws
            )

        assert session.status == "failed"


# ---------------------------------------------------------------------------
# _format_inputs
# ---------------------------------------------------------------------------

class TestFormatInputs:
    def test_single_file(self):
        f = _ingested_file(content=b"hello")
        result = PipelineOrchestrator._format_inputs([f])
        assert "test.txt" in result
        assert "hello" in result

    def test_multiple_files(self):
        f1 = _ingested_file(name="a.txt", content=b"AAA")
        f2 = _ingested_file(name="b.txt", content=b"BBB")
        result = PipelineOrchestrator._format_inputs([f1, f2])
        assert "a.txt" in result
        assert "AAA" in result
        assert "b.txt" in result
        assert "BBB" in result

    def test_empty_files(self):
        result = PipelineOrchestrator._format_inputs([])
        assert result == ""

    def test_latin1_fallback(self):
        content = bytes(range(128, 256))
        f = _ingested_file(content=content)
        result = PipelineOrchestrator._format_inputs([f])
        assert "test.txt" in result
