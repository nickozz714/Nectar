from __future__ import annotations

import httpx

from src.config import get_settings


def embed(text: str) -> list[float] | None:
    """Embed via the configured OpenAI-compatible endpoint; None when embeddings are off."""
    settings = get_settings()
    if not settings.embeddings_enabled:
        return None
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
