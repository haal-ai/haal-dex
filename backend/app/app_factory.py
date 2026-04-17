from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


def _create_base_app(app_name: str) -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=app_name,
        version="0.1.0",
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


def _include_routers(app: FastAPI, routers: Iterable) -> None:
    for router in routers:
        app.include_router(router)



def _register_health(app: FastAPI) -> None:
    async def health() -> dict:
        return {"status": "ok"}

    app.get("/health")(health)



def create_chat_app() -> FastAPI:
    settings = get_settings()
    from app.api.auth import router as auth_router
    from app.api.chat import router as chat_router
    from app.api.personalities import router as personalities_router

    app = _create_base_app(f"{settings.app_name} Chat")
    _include_routers(
        app,
        [
            auth_router,
            chat_router,
            personalities_router,
        ],
    )
    _register_health(app)
    return app



def create_builder_app() -> FastAPI:
    settings = get_settings()
    from app.api.auth import router as auth_router
    from app.api.config import router as config_router
    from app.api.debug import router as debug_router
    from app.api.files import router as files_router
    from app.api.metrics import router as metrics_router
    from app.api.output import router as output_router
    from app.api.pipeline import router as pipeline_router
    from app.api.replay import router as replay_router

    app = _create_base_app(f"{settings.app_name} Builder")
    _include_routers(
        app,
        [
            auth_router,
            config_router,
            debug_router,
            files_router,
            metrics_router,
            output_router,
            pipeline_router,
            replay_router,
        ],
    )
    _register_health(app)
    return app



def create_app() -> FastAPI:
    return create_chat_app()
