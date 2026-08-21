"""Bounded teacher-planning retrieval backed by Cloud SQL pgvector."""

from __future__ import annotations

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests

from agents.mock_data import format_evidence_for_prompt, get_mock_evidence
from config import (
    KIDSPARK_RAG_CACHE_TTL_SECONDS,
    KIDSPARK_RAG_ENABLED,
    KIDSPARK_RAG_RESULT_LIMIT,
    KIDSPARK_RAG_SERVICE_URL,
    KIDSPARK_RAG_TIMEOUT_SECONDS,
)
from retrieval.grade_bands import normalize_grade_band

logger = logging.getLogger(__name__)
_INGESTION_ROOT = Path(__file__).resolve().parents[1] / "ingestion"
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kidspark-rag")
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def _ingestion_retriever():
    root = str(_INGESTION_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.services.retrieval import templated_retrieve

    return templated_retrieve


def _cache_key(prompt: str, grade_band: str, seed_k: int) -> str:
    material = f"{grade_band}\n{seed_k}\n{' '.join(prompt.lower().split())}"
    return sha256(material.encode("utf-8")).hexdigest()


def _cached(key: str) -> dict[str, Any] | None:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        created_at, value = item
        if time.monotonic() - created_at > KIDSPARK_RAG_CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        result = deepcopy(value)
        result["cache_hit"] = True
        return result


def _store_cache(key: str, value: dict[str, Any]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), deepcopy(value))


def _retrieve_from_service(prompt: str, grade_band: str, seed_k: int) -> dict[str, Any]:
    response = requests.post(
        f"{KIDSPARK_RAG_SERVICE_URL}/api/v1/retrieve",
        json={
            "prompt": prompt,
            "grade_band": grade_band,
            "seed_k": seed_k,
            "k": max(seed_k * 4, 20),
            "rerank": False,
        },
        timeout=KIDSPARK_RAG_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _retrieve_direct(prompt: str, grade_band: str, seed_k: int) -> dict[str, Any]:
    return _ingestion_retriever()(
        prompt=prompt,
        grade_band=grade_band,
        seed_k=seed_k,
        k=max(seed_k * 4, 20),
        rerank=False,
    )


def evidence_trace(pack: dict[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for seed in pack.get("seeds", [])[:KIDSPARK_RAG_RESULT_LIMIT]:
        trace.append(
            {
                "node_id": seed.get("node_id"),
                "bundle_id": seed.get("bundle_id"),
                "doc_kind": seed.get("doc_kind"),
                "score": seed.get("score"),
            }
        )
    for policy in pack.get("policies", [])[:KIDSPARK_RAG_RESULT_LIMIT]:
        trace.append(
            {
                "rule_id": policy.get("rule_id") or policy.get("id"),
                "framework": policy.get("framework"),
                "bundle_id": policy.get("bundle_id"),
            }
        )
    return trace


def retrieve_teacher_evidence(
    prompt: str,
    grade_band: str | None,
    *,
    seed_k: int = 6,
) -> dict[str, Any]:
    canonical_grade = normalize_grade_band(grade_band)
    if not KIDSPARK_RAG_ENABLED:
        return _fallback_pack(canonical_grade, grade_band, "retrieval_disabled")

    key = _cache_key(prompt, canonical_grade, seed_k)
    cached = _cached(key)
    if cached is not None:
        return cached

    try:
        target = _retrieve_from_service if KIDSPARK_RAG_SERVICE_URL else _retrieve_direct
        future = _EXECUTOR.submit(target, prompt, canonical_grade, seed_k)
        result = future.result(timeout=KIDSPARK_RAG_TIMEOUT_SECONDS)
        result["source"] = (
            "rag_service" if KIDSPARK_RAG_SERVICE_URL else "cloud_sql_pgvector"
        )
        result["canonical_grade_band"] = canonical_grade
        result["cache_hit"] = False
        result["status"] = "ok" if result.get("seeds") or result.get("policies") else "empty"
        result["trace"] = evidence_trace(result)
        _store_cache(key, result)
        return result
    except TimeoutError:
        logger.warning("RAG retrieval timed out after %.1fs.", KIDSPARK_RAG_TIMEOUT_SECONDS)
        return _fallback_pack(canonical_grade, grade_band, "timeout")
    except Exception as exc:
        logger.warning("RAG retrieval unavailable; using static KidSpark evidence: %s", exc)
        return _fallback_pack(canonical_grade, grade_band, "unavailable", str(exc))


def _fallback_pack(
    canonical_grade: str,
    original_grade: str | None,
    status: str,
    error: str = "",
) -> dict[str, Any]:
    return {
        "source": "static_reference_fallback",
        "canonical_grade_band": canonical_grade,
        "status": status,
        "error": error,
        "fallback_text": format_evidence_for_prompt(
            get_mock_evidence(original_grade or "1st Grade")
        ),
        "seeds": [],
        "bundles": [],
        "policies": [],
        "trace": [],
        "cache_hit": False,
    }


def format_teacher_evidence(pack: dict[str, Any], max_chars: int = 12000) -> str:
    if pack.get("fallback_text"):
        return str(pack["fallback_text"])[:max_chars]
    lines = [
        f"Retrieval source: {pack.get('source')}",
        f"Canonical grade band: {pack.get('canonical_grade_band')}",
    ]
    for seed in pack.get("seeds", [])[:KIDSPARK_RAG_RESULT_LIMIT]:
        text = seed.get("text") or seed.get("content") or ""
        lines.append(
            f"- [{seed.get('doc_kind', 'reference')}/{seed.get('lesson_stage', 'general')}] "
            f"{text[:900]}"
        )
    for policy in pack.get("policies", [])[:KIDSPARK_RAG_RESULT_LIMIT]:
        text = policy.get("text") or policy.get("rule_text") or ""
        lines.append(f"- [policy {policy.get('framework', '')}] {text[:700]}")
    return "\n".join(lines)[:max_chars]
