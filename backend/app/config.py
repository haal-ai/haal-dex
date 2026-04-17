"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Central configuration for the INTENT backend.

    All values are read from environment variables with sensible defaults
    for local development.
    """

    # --- General ---
    app_name: str = "INTENT"
    debug: bool = False

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Database ---
    database_url: str = "sqlite:///./intent.db"

    # --- Auth / JWT ---
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # --- Chat provider ---
    chat_provider_type: str = "bedrock"
    chat_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    chat_aws_profile: str = ""
    chat_aws_region: str = ""
    chat_bedrock_inference_profile_id: str = ""
    chat_openai_endpoint: str = ""
    chat_openai_api_key: str = ""

    # --- CORS ---
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])

    # --- Encryption keys (per-target) ---
    encryption_key_input: str = ""
    encryption_key_output: str = ""
    encryption_key_log: str = ""

    # --- Storage ---
    upload_dir: str = "./uploads"
    log_dir: str = "./logs"
    faiss_index_dir: str = "./faiss_indexes"
    template_dir: str = "./templates"


def get_settings() -> Settings:
    """Build a ``Settings`` instance from the current environment."""
    return Settings(
        app_name=os.getenv("INTENT_APP_NAME", Settings.app_name),
        debug=os.getenv("INTENT_DEBUG", "false").lower() in ("true", "1", "yes"),
        host=os.getenv("INTENT_HOST", Settings.host),
        port=int(os.getenv("INTENT_PORT", str(Settings.port))),
        database_url=os.getenv("INTENT_DATABASE_URL", Settings.database_url),
        secret_key=os.getenv("INTENT_SECRET_KEY", Settings.secret_key),
        jwt_algorithm=os.getenv("INTENT_JWT_ALGORITHM", Settings.jwt_algorithm),
        jwt_expiration_minutes=int(
            os.getenv("INTENT_JWT_EXPIRATION_MINUTES", str(Settings.jwt_expiration_minutes))
        ),
        cors_origins=os.getenv("INTENT_CORS_ORIGINS", "http://localhost:5173").split(","),
        chat_provider_type=os.getenv("INTENT_CHAT_PROVIDER_TYPE", Settings.chat_provider_type),
        chat_model_id=os.getenv("INTENT_CHAT_MODEL_ID", Settings.chat_model_id),
        chat_aws_profile=os.getenv("INTENT_CHAT_AWS_PROFILE", ""),
        chat_aws_region=os.getenv("INTENT_CHAT_AWS_REGION", ""),
        chat_bedrock_inference_profile_id=os.getenv("INTENT_CHAT_BEDROCK_INFERENCE_PROFILE_ID", ""),
        chat_openai_endpoint=os.getenv("INTENT_CHAT_OPENAI_ENDPOINT", ""),
        chat_openai_api_key=os.getenv("INTENT_CHAT_OPENAI_API_KEY", ""),
        encryption_key_input=os.getenv("INTENT_ENCRYPTION_KEY_INPUT", ""),
        encryption_key_output=os.getenv("INTENT_ENCRYPTION_KEY_OUTPUT", ""),
        encryption_key_log=os.getenv("INTENT_ENCRYPTION_KEY_LOG", ""),
        upload_dir=os.getenv("INTENT_UPLOAD_DIR", Settings.upload_dir),
        log_dir=os.getenv("INTENT_LOG_DIR", Settings.log_dir),
        faiss_index_dir=os.getenv("INTENT_FAISS_INDEX_DIR", Settings.faiss_index_dir),
        template_dir=os.getenv("INTENT_TEMPLATE_DIR", Settings.template_dir),
    )
