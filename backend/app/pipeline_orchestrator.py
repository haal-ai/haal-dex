"""Pipeline orchestrator — wires the full flow from file upload through
pipeline execution to output generation.

Coordinates:
- FileIngestionService (with EncryptionService for decryption)
- GraphFactory (with ExecutionLogger and MetricsCollector callbacks)
- OutputGenerator (with EncryptionService for output encryption)
- Session management

Requirements: 1.1-1.5, 3.1-3.5, 7.3, 8.1-8.3, 9.1-9.4, 11.1-11.3,
              12.3-12.5, 13.1-13.3, 17.1-17.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.engine.graph_factory import GraphFactory, PipelineResult
from app.models.execution import ExecutionStep
from app.models.files import IngestedFile
from app.models.pipeline import PipelineConfig
from app.models.session import Session
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.encryption_service import EncryptionService
from app.services.execution_logger import ExecutionLogger
from app.services.metrics_collector import MetricsCollector
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry


class PipelineOrchestrator:
    """Wires file upload → pipeline execution → output generation.

    Integrates ExecutionLogger, MetricsCollector, and EncryptionService
    into the full pipeline flow.
    """

    def __init__(
        self,
        graph_factory: GraphFactory,
        execution_logger: ExecutionLogger,
        metrics_collector: MetricsCollector,
        output_generator: OutputGenerator,
        encryption_service: EncryptionService,
        template_registry: TemplateRegistry,
    ) -> None:
        self.graph_factory = graph_factory
        self.execution_logger = execution_logger
        self.metrics_collector = metrics_collector
        self.output_generator = output_generator
        self.encryption_service = encryption_service
        self.template_registry = template_registry

    # ------------------------------------------------------------------
    # Session creation
    # ------------------------------------------------------------------

    def create_session(self, user_id: str, config: PipelineConfig) -> Session:
        """Create a new session for a pipeline execution."""
        return Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            pipeline_config_id=config.name,
            status="pending",
            created_at=datetime.now(timezone.utc),
            completed_at=None,
            input_files=[],
            output_documents=[],
        )

    # ------------------------------------------------------------------
    # Full pipeline execution (non-streaming)
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        session: Session,
        config: PipelineConfig,
        ingested_files: list[IngestedFile],
    ) -> tuple[PipelineResult, RenderedDocument | None]:
        """Execute the full pipeline flow:

        1. Log session start
        2. Decrypt input files if needed
        3. Execute pipeline via GraphFactory with logging/metrics callbacks
        4. Generate output document via OutputGenerator
        5. Log session end

        Returns the pipeline result and the rendered output document (if any).
        """
        session.status = "running"
        session.input_files = [f.id for f in ingested_files]

        # 1. Log session start
        await self.execution_logger.log_session_start(
            session_id=session.id,
            user_id=session.user_id,
            inputs=ingested_files,
            config=config,
        )

        # 2. Decrypt input files if encryption is configured
        decrypted_files = await self._decrypt_files(ingested_files)

        # 3. Build shared state and execute pipeline
        input_text = self._format_inputs(decrypted_files)
        shared_state = {
            "session_id": session.id,
            "user_id": session.user_id,
            "input_files": decrypted_files,
        }

        try:
            result = await self.graph_factory.execute(
                config=config,
                input_data=input_text,
                shared_state=shared_state,
            )
        except Exception as exc:
            session.status = "failed"
            session.completed_at = datetime.now(timezone.utc)
            # Log the failure step
            await self._log_failure_step(session.id, str(exc))
            await self.execution_logger.log_session_end(session.id, [])
            raise

        # Record metrics from the execution result
        self._record_metrics_from_result(session.id, result)

        # Log execution steps from the result
        await self._log_execution_steps(session.id, result, config)

        # 4. Generate output if pipeline completed successfully
        rendered_doc: RenderedDocument | None = None
        if result.status == "COMPLETED":
            rendered_doc = await self._generate_output(
                session=session,
                config=config,
                pipeline_output=result.output or input_text,
            )

        # 5. Finalize session
        session.status = "completed" if result.status == "COMPLETED" else "failed"
        session.completed_at = datetime.now(timezone.utc)
        if rendered_doc:
            session.output_documents = [rendered_doc.id]

        await self.execution_logger.log_session_end(
            session.id,
            [rendered_doc] if rendered_doc else [],
        )

        return result, rendered_doc

    # ------------------------------------------------------------------
    # Streaming pipeline execution
    # ------------------------------------------------------------------

    async def stream_pipeline(
        self,
        session: Session,
        config: PipelineConfig,
        ingested_files: list[IngestedFile],
        websocket: Any,
    ) -> tuple[PipelineResult, RenderedDocument | None]:
        """Execute the pipeline with streaming events forwarded to WebSocket.

        Same flow as ``run_pipeline`` but uses ``stream_execute`` to forward
        real-time events (agent_start, llm_token, agent_complete,
        pipeline_complete) to the WebSocket while logging and collecting
        metrics.
        """
        session.status = "running"
        session.input_files = [f.id for f in ingested_files]

        await self.execution_logger.log_session_start(
            session_id=session.id,
            user_id=session.user_id,
            inputs=ingested_files,
            config=config,
        )

        decrypted_files = await self._decrypt_files(ingested_files)
        input_text = self._format_inputs(decrypted_files)
        shared_state = {
            "session_id": session.id,
            "user_id": session.user_id,
            "input_files": decrypted_files,
        }

        try:
            result = await self.graph_factory.stream_execute(
                config=config,
                input_data=input_text,
                shared_state=shared_state,
                websocket=websocket,
            )
        except Exception as exc:
            session.status = "failed"
            session.completed_at = datetime.now(timezone.utc)
            await self._log_failure_step(session.id, str(exc))
            await self.execution_logger.log_session_end(session.id, [])
            raise

        self._record_metrics_from_result(session.id, result)
        await self._log_execution_steps(session.id, result, config)

        rendered_doc: RenderedDocument | None = None
        if result.status == "COMPLETED":
            rendered_doc = await self._generate_output(
                session=session,
                config=config,
                pipeline_output=result.output or input_text,
            )

        session.status = "completed" if result.status == "COMPLETED" else "failed"
        session.completed_at = datetime.now(timezone.utc)
        if rendered_doc:
            session.output_documents = [rendered_doc.id]

        await self.execution_logger.log_session_end(
            session.id,
            [rendered_doc] if rendered_doc else [],
        )

        return result, rendered_doc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _decrypt_files(
        self, files: list[IngestedFile]
    ) -> list[IngestedFile]:
        """Decrypt files using the input encryption config if enabled."""
        input_config = self.encryption_service.get_config("input")
        if not input_config.enabled:
            return files

        from app.services.file_ingestion import FileIngestionService

        ingestion = FileIngestionService(encryption_service=self.encryption_service)
        decrypted: list[IngestedFile] = []
        for f in files:
            decrypted.append(await ingestion.decrypt_if_needed(f, input_config))
        return decrypted

    async def _generate_output(
        self,
        session: Session,
        config: PipelineConfig,
        pipeline_output: Any,
    ) -> RenderedDocument | None:
        """Render the pipeline output using the configured template."""
        template_id = config.output.template
        if not template_id:
            return None

        try:
            self.template_registry.get_template(template_id)
        except ValueError:
            return None

        metadata = DocumentMetadata(
            author=session.user_id,
            date=datetime.now(timezone.utc),
            version="1.0",
            classification="internal",
        )

        data = {"content": str(pipeline_output)}

        rendered = await self.output_generator.render(
            template_id=template_id,
            data=data,
            metadata=metadata,
            session_id=session.id,
        )

        return rendered

    def _record_metrics_from_result(
        self, session_id: str, result: PipelineResult
    ) -> None:
        """Record metrics for each agent in the execution order."""
        for agent_id in result.execution_order:
            # Record a baseline metric entry for each agent that executed
            self.metrics_collector.record(
                session_id=session_id,
                agent_id=agent_id,
                input_tokens=0,
                output_tokens=0,
            )

    async def _log_execution_steps(
        self, session_id: str, result: PipelineResult, config: PipelineConfig
    ) -> None:
        """Log an execution step for each agent in the execution order."""
        agent_map = {a.name: a for a in config.agents}
        for step_num, agent_id in enumerate(result.execution_order):
            agent_cfg = agent_map.get(agent_id)
            status = "completed"
            if result.status == "FAILED" and result.failed_agent == agent_id:
                status = "failed"

            step = ExecutionStep(
                step_number=step_num,
                agent_id=agent_id,
                agent_name=agent_id,
                status=status,
                timestamp=datetime.now(timezone.utc),
                input_data={},
                prompts_sent=[],
                llm_responses=[],
                llm_provider=agent_cfg.provider_config.provider_type if agent_cfg else "",
                llm_model=agent_cfg.provider_config.model_id if agent_cfg else "",
                decisions=[],
                output_data={},
                error=result.error if status == "failed" else None,
            )
            await self.execution_logger.log_step(session_id, step)

    async def _log_failure_step(self, session_id: str, error: str) -> None:
        """Log a single failure step when the pipeline raises an exception."""
        step = ExecutionStep(
            step_number=0,
            agent_id="pipeline",
            agent_name="pipeline",
            status="failed",
            timestamp=datetime.now(timezone.utc),
            input_data={},
            prompts_sent=[],
            llm_responses=[],
            llm_provider="",
            llm_model="",
            decisions=[],
            output_data={},
            error=error,
        )
        await self.execution_logger.log_step(session_id, step)

    @staticmethod
    def _format_inputs(files: list[IngestedFile]) -> str:
        """Concatenate file contents into a single input string."""
        parts: list[str] = []
        for f in files:
            try:
                text = f.content.decode("utf-8")
            except UnicodeDecodeError:
                text = f.content.decode("latin-1")
            parts.append(f"--- {f.original_name} ---\n{text}")
        combined = "\n\n".join(parts)
        if not combined.strip():
            return "No input text was provided."
        return combined
