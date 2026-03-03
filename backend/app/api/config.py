"""Pipeline configuration CRUD endpoints — admin-only access."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.middleware.auth import require_admin
from app.models.auth import UserContext
from app.models.pipeline import PipelineConfig
from app.services.config_parser import ConfigParseError, parse_config, serialize_config
from app.services.config_validator import validate_config

router = APIRouter(prefix="/api/config", tags=["config"])

# ---------------------------------------------------------------------------
# In-memory store (keyed by pipeline config name)
# ---------------------------------------------------------------------------

_pipeline_store: dict[str, PipelineConfig] = {}


def get_pipeline_store() -> dict[str, PipelineConfig]:
    """Return the in-memory pipeline config store (overridable in tests)."""
    return _pipeline_store


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PipelineConfigPayload(BaseModel):
    """Raw pipeline config payload sent by the client."""

    raw: str
    format: str  # "yaml" or "json"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pipelines")
async def list_pipelines(
    _user: UserContext = Depends(require_admin),
    store: dict[str, PipelineConfig] = Depends(get_pipeline_store),
) -> dict[str, Any]:
    """List all stored pipeline configurations. Admin only."""
    return {
        "pipelines": [
            {"name": name, "config": _config_to_dict(cfg)}
            for name, cfg in store.items()
        ],
    }


@router.get("/pipelines/{name}")
async def get_pipeline(
    name: str,
    _user: UserContext = Depends(require_admin),
    store: dict[str, PipelineConfig] = Depends(get_pipeline_store),
) -> dict[str, Any]:
    """Get a specific pipeline configuration by name. Admin only."""
    if name not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline config '{name}' not found",
        )
    return {"name": name, "config": _config_to_dict(store[name])}


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: PipelineConfigPayload,
    _user: UserContext = Depends(require_admin),
    store: dict[str, PipelineConfig] = Depends(get_pipeline_store),
) -> dict[str, Any]:
    """Create a new pipeline configuration. Admin only.

    The raw config string is parsed, validated, then stored.
    """
    config = _parse_and_validate(payload)

    if config.name in store:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pipeline config '{config.name}' already exists",
        )

    store[config.name] = config
    return {"name": config.name, "config": _config_to_dict(config)}


@router.put("/pipelines/{name}")
async def update_pipeline(
    name: str,
    payload: PipelineConfigPayload,
    _user: UserContext = Depends(require_admin),
    store: dict[str, PipelineConfig] = Depends(get_pipeline_store),
) -> dict[str, Any]:
    """Update an existing pipeline configuration. Admin only."""
    if name not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline config '{name}' not found",
        )

    config = _parse_and_validate(payload)

    # Remove old key if the name changed
    if config.name != name:
        del store[name]

    store[config.name] = config
    return {"name": config.name, "config": _config_to_dict(config)}


@router.delete("/pipelines/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    name: str,
    _user: UserContext = Depends(require_admin),
    store: dict[str, PipelineConfig] = Depends(get_pipeline_store),
) -> None:
    """Delete a pipeline configuration. Admin only."""
    if name not in store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline config '{name}' not found",
        )
    del store[name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_and_validate(payload: PipelineConfigPayload) -> PipelineConfig:
    """Parse raw config, validate it, and return the PipelineConfig."""
    try:
        config = parse_config(payload.raw, payload.format)
    except ConfigParseError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": exc.message,
                "location": exc.location,
                "nature": exc.nature,
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    errors = validate_config(config)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"validation_errors": errors},
        )

    return config


def _config_to_dict(config: PipelineConfig) -> dict[str, Any]:
    """Convert a PipelineConfig to a JSON-serializable dict."""
    return asdict(config)
