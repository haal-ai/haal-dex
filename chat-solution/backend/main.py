from __future__ import annotations

import sys
from pathlib import Path

ROOT_BACKEND = Path(__file__).resolve().parents[2] / 'backend'
if str(ROOT_BACKEND) not in sys.path:
    sys.path.insert(0, str(ROOT_BACKEND))

from app.chat_main import app
