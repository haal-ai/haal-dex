"""Pipeline configuration CRUD endpoints — admin-only access."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.middleware.auth import require_admin
from app.models.auth import UserContext
from app.models.pipeline import AgentConfig, OAuthConfig, OutputConfig, PipelineConfig, ProviderConfig
from app.services.config_parser import ConfigParseError, parse_config, serialize_config
from app.services.config_validator import validate_config

router = APIRouter(prefix="/api/config", tags=["config"])

# ---------------------------------------------------------------------------
# In-memory store (keyed by pipeline config name)
# ---------------------------------------------------------------------------

_store_lock = Lock()
_default_store_path = Path(__file__).resolve().parents[3] / "pipeline_store.json"
_store_path = Path(os.getenv("INTENT_PIPELINE_STORE_PATH", str(_default_store_path)))


def _dict_to_config(data: dict[str, Any]) -> PipelineConfig:
    output = data.get("output") or {}
    output_cfg = OutputConfig(
        template=str(output.get("template") or ""),
        formats=list(output.get("formats") or []),
    )

    agents: list[AgentConfig] = []
    for a in list(data.get("agents") or []):
        provider = a.get("provider_config") or {}
        oauth_raw = provider.get("oauth_config")
        oauth_cfg = OAuthConfig(**oauth_raw) if isinstance(oauth_raw, dict) else None
        provider_cfg = ProviderConfig(
            provider_type=str(provider.get("provider_type") or ""),
            model_id=str(provider.get("model_id") or ""),
            inference_profile_id=provider.get("inference_profile_id"),
            endpoint=provider.get("endpoint"),
            api_key=provider.get("api_key"),
            region=provider.get("region"),
            temperature=float(provider.get("temperature") or 0.7),
            max_tokens=int(provider.get("max_tokens") or 2048),
            oauth_config=oauth_cfg,
        )
        agents.append(
            AgentConfig(
                name=str(a.get("name") or ""),
                model=str(a.get("model") or ""),
                provider_config=provider_cfg,
                description=str(a.get("description") or ""),
                system_prompt=a.get("system_prompt"),
                faiss_indexes=list(a.get("faiss_indexes") or []),
                tools=list(a.get("tools") or []),
                template=a.get("template"),
            )
        )

    return PipelineConfig(
        name=str(data.get("name") or ""),
        agents=agents,
        output=output_cfg,
        execution_timeout=int(data.get("execution_timeout") or 600),
    )


def _load_pipeline_store() -> dict[str, PipelineConfig]:
    if not _store_path.exists():
        return {}
    try:
        raw = json.loads(_store_path.read_text(encoding="utf-8"))
        pipelines = raw.get("pipelines") if isinstance(raw, dict) else None
        if not isinstance(pipelines, dict):
            return {}
        loaded: dict[str, PipelineConfig] = {}
        for name, cfg in pipelines.items():
            if isinstance(cfg, dict):
                loaded[str(name)] = _dict_to_config(cfg)
        return loaded
    except Exception:
        return {}


def _persist_pipeline_store(store: dict[str, PipelineConfig]) -> None:
    _store_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _store_path.with_suffix(_store_path.suffix + ".tmp")
    payload = {"pipelines": {name: asdict(cfg) for name, cfg in store.items()}}
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_store_path)


_pipeline_store: dict[str, PipelineConfig] = _load_pipeline_store()


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

    with _store_lock:
        store[config.name] = config
        _persist_pipeline_store(store)
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

    with _store_lock:
        # Remove old key if the name changed
        if config.name != name:
            del store[name]

        store[config.name] = config
        _persist_pipeline_store(store)
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
    with _store_lock:
        del store[name]
        _persist_pipeline_store(store)


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
