"""Execution logger with structured JSON logging.

Records full execution traces — per-step data (timestamp with timezone,
agent ID, input data, prompts, LLM responses, decisions, output data,
user identity, LLM provider/model) and per-session data (input files,
output documents, pipeline config).

Logs are stored as JSON files on the file system, one file per session.
Optionally encrypts logs at rest via EncryptionService.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.config import Settings, get_settings
from app.models.encryption import EncryptionConfig
from app.models.execution import ExecutionStep, SessionLog
from app.models.files import IngestedFile
from app.models.pipeline import PipelineConfig
from app.models.templates import RenderedDocument
from app.services.encryption_service import EncryptionService

logger = structlog.get_logger(__name__)


def _datetime_serializer(obj: Any) -> str:
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _step_to_dict(step: ExecutionStep) -> dict:
    """Convert an ExecutionStep dataclass to a plain dict."""
    return {
        "step_number": step.step_number,
        "agent_id": step.agent_id,
        "agent_name": step.agent_name,
        "status": step.status,
        "timestamp": step.timestamp.isoformat(),
        "input_data": step.input_data,
        "prompts_sent": step.prompts_sent,
        "llm_responses": step.llm_responses,
        "llm_provider": step.llm_provider,
        "llm_model": step.llm_model,
        "decisions": step.decisions,
        "output_data": step.output_data,
        "error": step.error,
    }


def _ingested_file_to_dict(f: IngestedFile) -> dict:
    """Convert an IngestedFile to a JSON-safe dict.

    File content (bytes) is stored as a latin-1 string so it round-trips
    losslessly through JSON without base64 overhead for typical text files.
    """
    return {
        "id": f.id,
        "original_name": f.original_name,
        "format": f.format,
        "size_bytes": f.size_bytes,
        "content": f.content.decode("latin-1"),
        "was_encrypted": f.was_encrypted,
        "session_id": f.session_id,
    }


def _rendered_doc_to_dict(doc: RenderedDocument) -> dict:
    """Convert a RenderedDocument to a JSON-safe dict."""
    return {
        "id": doc.id,
        "session_id": doc.session_id,
        "template_id": doc.template_id,
        "format": doc.format,
        "content": doc.content.decode("latin-1"),
        "metadata": {
            "author": doc.metadata.author,
            "date": doc.metadata.date.isoformat(),
            "version": doc.metadata.version,
            "classification": doc.metadata.classification,
        },
        "validation_result": doc.validation_result,
    }


def _pipeline_config_to_dict(config: PipelineConfig) -> dict:
    """Serialize PipelineConfig to a plain dict."""
    return {
        "name": config.name,
        "execution_timeout": config.execution_timeout,
        "agents": [
            {
                "name": a.name,
                "model": a.model,
                "description": a.description,
                "tools": a.tools,
                "faiss_indexes": a.faiss_indexes,
            }
            for a in config.agents
        ],
        "output": {
            "template": config.output.template,
            "formats": config.output.formats,
        },
    }


class ExecutionLogger:
    """Structured JSON execution logger.

    Each session is stored as a single JSON file: ``<log_dir>/<session_id>.json``.
    When log encryption is enabled the JSON payload is encrypted at rest.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        encryption_service: EncryptionService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._encryption_service = encryption_service or EncryptionService(self._settings)
        self._log_dir = Path(self._settings.log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def log_step(self, session_id: str, step: ExecutionStep) -> None:
        """Append an execution step to the session log."""
        session_data = self._read_session_file(session_id)
        session_data.setdefault("steps", []).append(_step_to_dict(step))
        self._write_session_file(session_id, session_data)
        logger.info(
            "execution_step_logged",
            session_id=session_id,
            step_number=step.step_number,
            agent_id=step.agent_id,
        )

    async def log_session_start(
        self,
        session_id: str,
        user_id: str,
        inputs: list[IngestedFile],
        config: PipelineConfig,
    ) -> None:
        """Record the start of a pipeline session."""
        session_data: dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "pipeline_config": _pipeline_config_to_dict(config),
            "input_files": [_ingested_file_to_dict(f) for f in inputs],
            "output_documents": [],
            "steps": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        self._write_session_file(session_id, session_data)
        logger.info("session_started", session_id=session_id, user_id=user_id)

    async def log_session_end(
        self,
        session_id: str,
        outputs: list[RenderedDocument],
    ) -> None:
        """Record the end of a pipeline session with output documents."""
        session_data = self._read_session_file(session_id)
        session_data["output_documents"] = [_rendered_doc_to_dict(d) for d in outputs]
        session_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write_session_file(session_id, session_data)
        logger.info("session_ended", session_id=session_id)

    async def get_session_log(self, session_id: str) -> SessionLog:
        """Load and return a full SessionLog for the given session."""
        data = self._read_session_file(session_id)
        return self._dict_to_session_log(data)

    async def list_sessions(self, filters: dict | None = None) -> list[dict]:
        """Return summary info for stored sessions, optionally filtered."""
        filters = filters or {}
        summaries: list[dict] = []
        for path in sorted(self._log_dir.glob("*.json")):
            try:
                data = self._read_session_file(path.stem)
            except Exception:
                continue
            summary = {
                "session_id": data.get("session_id", path.stem),
                "user_id": data.get("user_id", ""),
                "created_at": data.get("created_at", ""),
                "completed_at": data.get("completed_at"),
                "step_count": len(data.get("steps", [])),
            }
            if self._matches_filters(summary, filters):
                summaries.append(summary)
        return summaries

    # ------------------------------------------------------------------
    # File I/O with optional encryption
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        return self._log_dir / f"{session_id}.json"

    def _get_encryption_config(self) -> EncryptionConfig:
        return self._encryption_service.get_config("log")

    def _write_session_file(self, session_id: str, data: dict) -> None:
        """Write session data as JSON, encrypting if configured."""
        json_bytes = json.dumps(data, default=_datetime_serializer).encode("utf-8")
        enc_config = self._get_encryption_config()
        if enc_config.enabled:
            json_bytes = self._encryption_service.encrypt(json_bytes, enc_config)
        self._session_path(session_id).write_bytes(json_bytes)

    def _read_session_file(self, session_id: str) -> dict:
        """Read session data from JSON file, decrypting if needed."""
        path = self._session_path(session_id)
        if not path.exists():
            return {}
        raw = path.read_bytes()
        enc_config = self._get_encryption_config()
        if enc_config.enabled:
            raw = self._encryption_service.decrypt(raw, enc_config)
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filters(summary: dict, filters: dict) -> bool:
        """Return True if *summary* matches all *filters*."""
        for key, value in filters.items():
            if summary.get(key) != value:
                return False
        return True

    @staticmethod
    def _dict_to_session_log(data: dict) -> SessionLog:
        """Reconstruct a SessionLog from a raw dict."""
        steps = [
            ExecutionStep(
                step_number=s["step_number"],
                agent_id=s["agent_id"],
                agent_name=s["agent_name"],
                status=s["status"],
                timestamp=datetime.fromisoformat(s["timestamp"]),
                input_data=s["input_data"],
                prompts_sent=s["prompts_sent"],
                llm_responses=s["llm_responses"],
                llm_provider=s["llm_provider"],
                llm_model=s["llm_model"],
                decisions=s["decisions"],
                output_data=s["output_data"],
                error=s.get("error"),
            )
            for s in data.get("steps", [])
        ]

        input_files = [
            IngestedFile(
                id=f["id"],
                original_name=f["original_name"],
                format=f["format"],
                size_bytes=f["size_bytes"],
                content=f["content"].encode("latin-1"),
                was_encrypted=f["was_encrypted"],
                session_id=f["session_id"],
            )
            for f in data.get("input_files", [])
        ]

        output_documents = [
            RenderedDocument(
                id=d["id"],
                session_id=d["session_id"],
                template_id=d["template_id"],
                format=d["format"],
                content=d["content"].encode("latin-1"),
                metadata=_parse_doc_metadata(d["metadata"]),
                validation_result=d.get("validation_result", []),
            )
            for d in data.get("output_documents", [])
        ]

        # Reconstruct a minimal PipelineConfig for the log
        pc_data = data.get("pipeline_config", {})
        from app.models.pipeline import AgentConfig, OutputConfig, ProviderConfig

        agents = [
            AgentConfig(
                name=a["name"],
                model=a.get("model", ""),
                provider_config=ProviderConfig(provider_type="", model_id=""),
                description=a.get("description", ""),
                tools=a.get("tools", []),
                faiss_indexes=a.get("faiss_indexes", []),
            )
            for a in pc_data.get("agents", [])
        ]
        output_cfg = OutputConfig(
            template=pc_data.get("output", {}).get("template", ""),
            formats=pc_data.get("output", {}).get("formats", []),
        )
        pipeline_config = PipelineConfig(
            name=pc_data.get("name", ""),
            agents=agents,
            output=output_cfg,
            execution_timeout=pc_data.get("execution_timeout", 600),
        )

        return SessionLog(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            pipeline_config=pipeline_config,
            steps=steps,
            input_files=input_files,
            output_documents=output_documents,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


def _parse_doc_metadata(meta: dict) -> "DocumentMetadata":
    from app.models.templates import DocumentMetadata

    return DocumentMetadata(
        author=meta["author"],
        date=datetime.fromisoformat(meta["date"]),
        version=meta["version"],
        classification=meta["classification"],
    )
