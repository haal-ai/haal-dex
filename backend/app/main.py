"""INTENT backend – FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from app.app_factory import create_chat_app as _create_app


def create_app() -> FastAPI:
    """Build and configure the chat backend application."""
    return _create_app()


app = create_app()
