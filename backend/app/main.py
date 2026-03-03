"""INTENT backend – FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.config import router as config_router
from app.api.debug import router as debug_router
from app.api.files import router as files_router
from app.api.personalities import router as personalities_router
from app.api.metrics import router as metrics_router
from app.api.output import router as output_router
from app.api.pipeline import router as pipeline_router
from app.api.replay import router as replay_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(config_router)
    app.include_router(debug_router)
    app.include_router(files_router)
    app.include_router(personalities_router)
    app.include_router(metrics_router)
    app.include_router(output_router)
    app.include_router(pipeline_router)
    app.include_router(replay_router)

    # --- Health check ---
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
