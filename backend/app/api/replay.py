"""Replay API endpoints for step-by-step execution replay."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.services.replay_engine import ReplayEngine

router = APIRouter(prefix="/api/replay", tags=["replay"])

_engine = ReplayEngine()


def get_replay_engine() -> ReplayEngine:
    """Dependency that returns the shared ReplayEngine instance."""
    return _engine


@router.get("/{session_id}")
async def get_replay(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    engine: ReplayEngine = Depends(get_replay_engine),
) -> dict:
    """Load a full execution replay for a session."""
    try:
        replay = await engine.load_execution(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "session_id": replay.session_id,
        "user_id": replay.user_id,
        "created_at": replay.created_at.isoformat(),
        "completed_at": replay.completed_at.isoformat() if replay.completed_at else None,
        "steps": [_step_to_dict(s) for s in replay.steps],
        "timeline": [_timeline_entry_to_dict(e) for e in replay.timeline],
    }


@router.get("/{session_id}/step/{step_number}")
async def get_replay_step(
    session_id: str,
    step_number: int,
    user: UserContext = Depends(get_current_user),
    engine: ReplayEngine = Depends(get_replay_engine),
) -> dict:
    """Return a single replay step."""
    try:
        step = await engine.get_step(session_id, step_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return _step_to_dict(step)


def _step_to_dict(step) -> dict:
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


def _timeline_entry_to_dict(entry) -> dict:
    return {
        "step_number": entry.step_number,
        "agent_id": entry.agent_id,
        "agent_name": entry.agent_name,
        "status": entry.status,
        "timestamp": entry.timestamp.isoformat(),
    }
