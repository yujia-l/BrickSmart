"""Vertex Gemini model router with a bounded primary/fallback policy."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from config import (
    GCP_PROJECT_ID,
    GEMINI_API_KEY,
    GEMINI_FALLBACK_MODEL,
    GEMINI_PRIMARY_MODEL,
    KIDSPARK_OFFLINE_MODE,
    LLM_PROVIDER,
    VERTEX_GENERATION_LOCATION,
)

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class GeminiGenerationError(RuntimeError):
    """Raised after both configured Gemini models fail."""


def provider_configured() -> bool:
    return (
        LLM_PROVIDER == "vertex"
        and bool(GEMINI_API_KEY or GCP_PROJECT_ID)
        and not KIDSPARK_OFFLINE_MODE
        and not os.getenv("PYTEST_CURRENT_TEST")
    )


def _client():
    from google import genai

    if GEMINI_API_KEY:
        return genai.Client(vertexai=True, api_key=GEMINI_API_KEY)
    return genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=VERTEX_GENERATION_LOCATION,
    )


def auth_mode() -> str:
    """Return the active non-sensitive Vertex authentication mode."""
    if GEMINI_API_KEY:
        return "api_key"
    if GCP_PROJECT_ID:
        return "application_default_credentials"
    return "unconfigured"


def _config(
    system: str,
    temperature: float,
    max_output_tokens: int,
    response_schema: type[BaseModel] | dict[str, Any] | None = None,
):
    from google.genai import types

    kwargs: dict[str, Any] = {
        "system_instruction": system,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "thinking_config": types.ThinkingConfig(thinking_budget=0),
    }
    if response_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = response_schema
    return types.GenerateContentConfig(**kwargs)


def _generate(
    *,
    system: str,
    user: str,
    temperature: float,
    max_output_tokens: int,
    response_schema: type[BaseModel] | dict[str, Any] | None = None,
) -> str:
    if not provider_configured():
        raise GeminiGenerationError("Vertex Gemini is not configured for this runtime.")

    errors: list[str] = []
    client = _client()
    for index, model in enumerate((GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL)):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user,
                config=_config(system, temperature, max_output_tokens, response_schema),
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("model returned an empty response")
            if index:
                logger.warning("Gemini fallback model %s completed the request.", model)
            return text
        except Exception as exc:
            errors.append(f"{model}: {exc}")
            logger.warning("Gemini model %s failed: %s", model, exc)
            if index == 0:
                time.sleep(0.4)
    raise GeminiGenerationError("Both Gemini models failed. " + " | ".join(errors))


def generate_text(
    system: str,
    user: str,
    *,
    temperature: float = 0.5,
    max_output_tokens: int = 1200,
) -> str:
    return _generate(
        system=system,
        user=user,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def generate_json(
    system: str,
    user: str,
    *,
    schema: type[SchemaT] | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 2400,
) -> SchemaT | dict[str, Any]:
    text = _generate(
        system=system,
        user=user,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_schema=schema or {"type": "object"},
    )
    if schema is not None:
        return schema.model_validate_json(text)
    return json.loads(text)
