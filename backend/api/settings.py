"""
Runtime settings endpoints for local KidSpark demos.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config

router = APIRouter(prefix="/api/v1", tags=["settings"])

OPENAI_KEY_FILE = Path(__file__).resolve().parents[2] / "openai.key"


class OpenAIKeyRequest(BaseModel):
    api_key: str


def _mask_key(value: str) -> str:
    if not value:
        return ""
    return f"{value[:7]}...{value[-4:]}" if len(value) > 12 else "configured"


def _current_key() -> str:
    if config.OPENAI_API_KEY:
        return config.OPENAI_API_KEY
    if OPENAI_KEY_FILE.exists():
        return OPENAI_KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def _apply_openai_key(api_key: str) -> None:
    os.environ["OPENAI_API_KEY"] = api_key
    config.OPENAI_API_KEY = api_key
    for module_name in [
        "agents.consultation",
        "agents.story_analysis",
        "agents.block_awareness",
        "build3d.pipeline",
    ]:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, "OPENAI_API_KEY"):
            setattr(module, "OPENAI_API_KEY", api_key)


@router.get("/settings/openai-key")
async def get_openai_key_status():
    key = _current_key()
    if key:
        _apply_openai_key(key)
    return {
        "configured": bool(key),
        "masked": _mask_key(key),
        "source": "openai.key" if OPENAI_KEY_FILE.exists() else "environment",
    }


@router.post("/settings/openai-key")
async def set_openai_key(body: OpenAIKeyRequest):
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key is required.")
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="OpenAI API key should start with sk-.")
    OPENAI_KEY_FILE.write_text(api_key, encoding="utf-8")
    _apply_openai_key(api_key)
    return {
        "configured": True,
        "masked": _mask_key(api_key),
        "source": "openai.key",
    }
