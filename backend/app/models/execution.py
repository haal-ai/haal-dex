from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.files import IngestedFile
from app.models.pipeline import PipelineConfig
from app.models.templates import RenderedDocument


@dataclass
class ExecutionStep:
    step_number: int
    agent_id: str
    agent_name: str
    status: str  # "pending" | "running" | "completed" | "failed"
    timestamp: datetime  # with timezone
    input_data: dict
    prompts_sent: list[str]
    llm_responses: list[str]
    llm_provider: str
    llm_model: str
    decisions: list[str]
    output_data: dict
    error: str | None


@dataclass
class SessionLog:
    session_id: str
    user_id: str
    pipeline_config: PipelineConfig
    steps: list[ExecutionStep]
    input_files: list[IngestedFile]
    output_documents: list[RenderedDocument]
    created_at: datetime
    completed_at: datetime | None
