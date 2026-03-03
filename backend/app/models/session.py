from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:
    id: str
    user_id: str
    pipeline_config_id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    created_at: datetime
    completed_at: datetime | None
    input_files: list[str]  # IngestedFile IDs
    output_documents: list[str]  # RenderedDocument IDs
