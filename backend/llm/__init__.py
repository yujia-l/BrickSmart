"""Shared language-model adapters for KidSpark."""

from llm.vertex_gemini import (
    auth_mode,
    generate_json,
    generate_text,
    provider_configured,
)

__all__ = ["auth_mode", "generate_json", "generate_text", "provider_configured"]
