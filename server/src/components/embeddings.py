from __future__ import annotations

import httpx

from src.components.config import get_settings

_local_model = None


def _local():
    global _local_model
    if _local_model is None:
        from fastembed import TextEmbedding

        _local_model = TextEmbedding(get_settings().EMBEDDINGS_MODEL)
    return _local_model


def embed(text: str) -> list[float] | None:
    """Local-first: in-process fastembed (no cloud, offline). An OpenAI-compatible
    EMBEDDINGS_BASE_URL overrides local mode; None when embeddings are disabled."""
    settings = get_settings()
    if settings.EMBEDDINGS_BASE_URL:
        headers = {}
        if settings.EMBEDDINGS_API_KEY:
            headers["Authorization"] = f"Bearer {settings.EMBEDDINGS_API_KEY}"
        response = httpx.post(
            f"{settings.EMBEDDINGS_BASE_URL.rstrip('/')}/embeddings",
            json={"model": settings.EMBEDDINGS_MODEL, "input": text},
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    if settings.EMBEDDINGS_LOCAL and settings.EMBEDDINGS_MODEL:
        return list(_local().embed([text]))[0].tolist()
    return None


def warmup() -> None:
    """Load the local model at startup so the first request doesn't pay for it."""
    settings = get_settings()
    if settings.EMBEDDINGS_LOCAL and not settings.EMBEDDINGS_BASE_URL and settings.EMBEDDINGS_MODEL:
        _local()
