"""Vertex AI embedding helpers used by ingestion and retrieval."""

from __future__ import annotations

import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable


def _client(settings):
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT_ID,
        location=settings.VERTEX_EMBEDDING_LOCATION,
    )


def _embed(texts: Iterable[str], settings, task_type: str) -> list[list[float]]:
    from google.genai import types

    values = [str(text or " ") for text in texts]
    if not values:
        return []

    # gemini-embedding-001 accepts one text per request. Keep this boundary here
    # so callers can continue submitting lists without depending on model quirks.
    requests_per_minute = max(
        1, int(getattr(settings, "EMBED_REQUESTS_PER_MINUTE", 4))
    )
    request_interval = 60.0 / requests_per_minute
    rate_lock = threading.Lock()
    next_request_at = [time.monotonic()]

    def wait_for_quota_slot() -> None:
        with rate_lock:
            now = time.monotonic()
            scheduled = max(now, next_request_at[0])
            next_request_at[0] = scheduled + request_interval
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)

    def embed_one(value: str) -> list[float]:
        client = _client(settings)
        last_error: Exception | None = None
        for attempt in range(3):
            wait_for_quota_slot()
            try:
                response = client.models.embed_content(
                    model=settings.EMBED_MODEL,
                    contents=value,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=settings.EMBED_DIM,
                    ),
                )
                return list(response.embeddings[0].values)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    is_quota_error = "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)
                    time.sleep((30.0 if is_quota_error else 2.0) * (attempt + 1))
        raise RuntimeError("Vertex text embedding failed after three attempts.") from last_error

    workers = max(1, min(int(getattr(settings, "EMBED_WORKERS", 2)), 16))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vertex-embed") as pool:
        vectors = list(pool.map(embed_one, values))

    if any(len(vector) != settings.EMBED_DIM for vector in vectors):
        raise RuntimeError(
            f"Vertex embedding dimension mismatch; expected {settings.EMBED_DIM}."
        )
    return vectors


def embed_texts(texts, settings):
    return _embed(texts, settings, "RETRIEVAL_DOCUMENT")


def embed_query(text, settings):
    return _embed([text], settings, "RETRIEVAL_QUERY")[0]


def embed_image(image_bytes: bytes, contextual_text: str, settings) -> list[float]:
    """Generate a visual vector only for selected, instruction-relevant figures."""
    from google.auth import default
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    location = settings.VERTEX_EMBEDDING_LOCATION
    model_path = (
        f"projects/{settings.GCP_PROJECT_ID}/locations/{location}/"
        f"publishers/google/models/{settings.VISUAL_EMBED_MODEL}"
    )
    endpoint = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"{model_path}:predict"
    )
    payload = {
        "instances": [
            {
                "image": {
                    "bytesBase64Encoded": base64.b64encode(image_bytes).decode("ascii")
                },
                "text": contextual_text[:1000],
            }
        ],
        "parameters": {"dimension": settings.VISUAL_EMBED_DIM},
    }
    response = AuthorizedSession(credentials).post(endpoint, json=payload, timeout=90)
    response.raise_for_status()
    predictions = response.json().get("predictions") or []
    vector = list(predictions[0].get("imageEmbedding") or []) if predictions else []
    if len(vector) != settings.VISUAL_EMBED_DIM:
        raise RuntimeError(
            "Vertex visual embedding dimension mismatch; "
            f"expected {settings.VISUAL_EMBED_DIM}, received {len(vector)}."
        )
    return vector
