from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.personality_store import PersonalityStore

router = APIRouter(prefix="/api/personalities", tags=["personalities"])


def _get_store() -> PersonalityStore:
    backend_dir = Path(__file__).resolve().parents[2]
    store_path = backend_dir / "personalities_store.json"
    return PersonalityStore(store_path)


@router.get("/")
async def list_personalities() -> dict:
    store = _get_store()
    personalities = [store.to_public_dict(p) for p in store.list()]
    return {"personalities": personalities}


@router.get("/{personality_id}")
async def get_personality(personality_id: str) -> dict:
    store = _get_store()
    personality = store.get(personality_id)
    if personality is None:
        raise HTTPException(status_code=404, detail="Unknown personality")
    return store.to_public_dict(personality)
