"""Pipeline execution REST and WebSocket endpoints.

Provides:
- POST /api/pipeline/execute  — start a pipeline execution, return session_id + result
- WS   /api/ws/execution/{session_id} — stream execution events via WebSocket

Session management uses an in-memory dict to track sessions (session_id → status/result).
Uses PipelineOrchestrator to wire ExecutionLogger, MetricsCollector, and
EncryptionService into the full flow.

Requirements: 3.1, 3.2, 13.2, 17.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.engine.agent_factory import AgentFactory
from app.engine.graph_factory import GraphFactory, PipelineResult
from app.engine.model_factory import ModelFactory
from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.models.files import IngestedFile
from app.models.pipeline import PipelineConfig
from app.models.session import Session
from app.pipeline_orchestrator import PipelineOrchestrator
from app.services.encryption_service import EncryptionService
from app.services.execution_logger import ExecutionLogger
from app.services.metrics_collector import MetricsCollector
from app.services.output_generator import OutputGenerator
from app.services.template_registry import TemplateRegistry

router = APIRouter(tags=["pipeline"])

# ---------------------------------------------------------------------------
# In-memory session store and file store
# ---------------------------------------------------------------------------

_sessions: dict[str, Session] = {}
_session_files: dict[str, list[IngestedFile]] = {}


def get_sessions() -> dict[str, Session]:
    """Return the shared session store (overridable in tests)."""
    return _sessions


def get_session_files() -> dict[str, list[IngestedFile]]:
    """Return the shared session file store."""
    return _session_files


def store_session_files(session_id: str, files: list[IngestedFile]) -> None:
    """Store ingested files for a session for later pipeline use."""
    _session_files[session_id] = files


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_graph_factory() -> GraphFactory:
    """Return a GraphFactory wired with real factories.

    Overridable via ``app.dependency_overrides`` in tests.
    """
    model_factory = ModelFactory()
    agent_factory = AgentFactory(model_factory=model_factory)
    return GraphFactory(agent_factory=agent_factory)


def _get_orchestrator() -> PipelineOrchestrator:
    """Return a PipelineOrchestrator wired with all services.

    Overridable via ``app.dependency_overrides`` in tests.
    """
    encryption_service = EncryptionService()
    execution_logger = ExecutionLogger(encryption_service=encryption_service)
    metrics_collector = MetricsCollector()
    template_registry = TemplateRegistry()
    output_generator = OutputGenerator(
        registry=template_registry,
        encryption_service=encryption_service,
    )
    graph_factory = _get_graph_factory()

    return PipelineOrchestrator(
        graph_factory=graph_factory,
        execution_logger=execution_logger,
        metrics_collector=metrics_collector,
        output_generator=output_generator,
        encryption_service=encryption_service,
        template_registry=template_registry,
    )


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@router.post("/api/pipeline/execute")
async def execute_pipeline(
    config: PipelineConfig,
    user: UserContext = Depends(get_current_user),
    orchestrator: PipelineOrchestrator = Depends(_get_orchestrator),
) -> dict:
    """Execute a pipeline synchronously and return the session_id and result.

    Accepts a ``PipelineConfig`` in the request body, creates a new session,
    runs the full pipeline flow via PipelineOrchestrator (logging, metrics,
    encryption, output generation), and returns the outcome.
    """
    session = orchestrator.create_session(user.user_id, config)
    _sessions[session.id] = session

    # Retrieve any files stored for this session, or use empty list
    ingested_files = _session_files.get(session.id, [])

    try:
        result, rendered_doc = await orchestrator.run_pipeline(
            session=session,
            config=config,
            ingested_files=ingested_files,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {exc}",
        )

    # Store rendered doc for output preview/export
    if rendered_doc:
        from app.api.output import _rendered_docs
        _rendered_docs[session.id] = rendered_doc

    # Store session config for WebSocket replay
    store_session_config(session.id, config)

    return {
        "session_id": session.id,
        "status": result.status,
        "output": result.output,
        "execution_order": result.execution_order,
        "execution_time_ms": result.execution_time_ms,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/api/ws/execution/{session_id}")
async def ws_execution(
    websocket: WebSocket,
    session_id: str,
    orchestrator: PipelineOrchestrator = Depends(_get_orchestrator),
) -> None:
    """Stream pipeline execution events over WebSocket.

    The client connects with a ``session_id``.  The server looks up the
    session, runs the pipeline via PipelineOrchestrator.stream_pipeline()
    forwarding events (agent_start, llm_token, agent_complete,
    pipeline_complete) to the WebSocket while logging and collecting metrics,
    then closes the connection.
    """
    await websocket.accept()

    session = _sessions.get(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "detail": "Session not found"})
        await websocket.close(code=4004)
        return

    try:
        config_obj = _get_session_config(session_id)
        if config_obj is None:
            await websocket.send_json({"type": "error", "detail": "No pipeline config for session"})
            await websocket.close(code=4004)
            return

        ingested_files = _session_files.get(session_id, [])

        result, rendered_doc = await orchestrator.stream_pipeline(
            session=session,
            config=config_obj,
            ingested_files=ingested_files,
            websocket=websocket,
        )

        # Store rendered doc for output preview/export
        if rendered_doc:
            from app.api.output import _rendered_docs
            _rendered_docs[session_id] = rendered_doc

        # Send final pipeline_complete event
        await websocket.send_json({
            "type": "pipeline_complete",
            "session_id": session_id,
            "status": result.status,
            "execution_order": result.execution_order,
            "execution_time_ms": result.execution_time_ms,
        })

    except WebSocketDisconnect:
        session.status = "failed"
        session.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        session.status = "failed"
        session.completed_at = datetime.now(timezone.utc)
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass

    try:
        await websocket.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session config store (lightweight — maps session_id to PipelineConfig)
# ---------------------------------------------------------------------------

_session_configs: dict[str, PipelineConfig] = {}


def store_session_config(session_id: str, config: PipelineConfig) -> None:
    """Associate a PipelineConfig with a session for WebSocket execution."""
    _session_configs[session_id] = config


def _get_session_config(session_id: str) -> PipelineConfig | None:
    return _session_configs.get(session_id)
