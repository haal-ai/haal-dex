"""Metrics API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.middleware.auth import get_current_user
from app.models.auth import UserContext
from app.services.metrics_collector import MetricsCollector

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# Singleton collector shared across requests.
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Dependency that returns the shared MetricsCollector instance."""
    return _collector


@router.get("/{session_id}")
async def get_session_metrics(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    collector: MetricsCollector = Depends(get_metrics_collector),
) -> dict:
    """Return per-agent token and call metrics for a session."""
    metrics = collector.get_session_metrics(session_id)
    return {
        "session_id": metrics.session_id,
        "agent_metrics": [
            {
                "agent_id": am.agent_id,
                "agent_name": am.agent_name,
                "input_tokens": am.input_tokens,
                "output_tokens": am.output_tokens,
                "llm_call_count": am.llm_call_count,
            }
            for am in metrics.agent_metrics
        ],
    }


@router.get("/{session_id}/csv")
async def get_session_metrics_csv(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    collector: MetricsCollector = Depends(get_metrics_collector),
) -> Response:
    """Export session metrics as a downloadable CSV file."""
    csv_content = collector.export_csv(session_id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="metrics_{session_id}.csv"'},
    )
