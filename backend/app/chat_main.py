from __future__ import annotations

from fastapi import FastAPI

from app.app_factory import create_chat_app as _create_chat_app



def create_app() -> FastAPI:
    return _create_chat_app()


app = create_app()
