from __future__ import annotations

from fastapi import FastAPI

from app.app_factory import create_builder_app as _create_builder_app



def create_app() -> FastAPI:
    return _create_builder_app()


app = create_app()
