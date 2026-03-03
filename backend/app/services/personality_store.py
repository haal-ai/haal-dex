from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.models.personality import Personality, PersonalityAccess


class PersonalityStore:
    def __init__(self, store_path: str | Path) -> None:
        self._store_path = Path(store_path)
        self._base_dir = self._store_path.parent.parent.resolve()
        self._cache: dict[str, Personality] | None = None

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _load_raw(self) -> dict:
        if not self._store_path.exists():
            return {"personalities": {}}
        with self._store_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _parse_personality(self, data: dict) -> Personality:
        access_data = data.get("access") or {}
        access = PersonalityAccess(
            allowed_tools=list(access_data.get("allowed_tools") or []),
            allowed_read_roots=access_data.get("allowed_read_roots"),
            allowed_write_roots=access_data.get("allowed_write_roots"),
            allowed_faiss_indexes=access_data.get("allowed_faiss_indexes"),
        )
        return Personality(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            instructions=str(data.get("instructions") or ""),
            access=access,
        )

    def load(self, *, force: bool = False) -> dict[str, Personality]:
        if self._cache is not None and not force:
            return self._cache

        raw = self._load_raw()
        personalities: dict[str, Personality] = {}
        for pid, pdata in (raw.get("personalities") or {}).items():
            if isinstance(pdata, dict) and "id" not in pdata:
                pdata = {**pdata, "id": pid}
            personality = self._parse_personality(pdata)
            personalities[personality.id] = personality

        self._cache = personalities
        return personalities

    def list(self) -> list[Personality]:
        return sorted(self.load().values(), key=lambda p: p.name.lower())

    def get(self, personality_id: str) -> Personality | None:
        return self.load().get(personality_id)

    def to_public_dict(self, personality: Personality) -> dict:
        data = asdict(personality)
        data.pop("access", None)
        data["access"] = {
            "allowed_tools": list(personality.access.allowed_tools),
            "allowed_read_roots": personality.access.allowed_read_roots,
            "allowed_write_roots": personality.access.allowed_write_roots,
            "allowed_faiss_indexes": personality.access.allowed_faiss_indexes,
        }
        return data
