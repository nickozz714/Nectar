"""Local cross-encoder reranker (fastembed TextCrossEncoder, ONNX/CPU — no torch, no GPU, no
cloud). A cross-encoder scores the query and each candidate TOGETHER, so it judges relevance far
more precisely than the bi-encoder embeddings used for first-stage retrieval. We rerank only the
top-K hybrid candidates, keeping cost bounded. Fully local — preserves Nectar's no-cloud property.

Everything is best-effort: if the model can't load (offline, unsupported fastembed), rerank()
returns None and the caller simply keeps the first-stage order."""
from __future__ import annotations

import logging

from src.components.config import get_settings

_log = logging.getLogger("nectar")
_model = None
_loaded = False   # we attempted a load (success or failure) — don't retry every call


def _get_model():
    global _model, _loaded
    if _loaded:
        return _model
    _loaded = True
    settings = get_settings()
    if not settings.RERANK_ENABLED:
        return None
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _model = TextCrossEncoder(model_name=settings.RERANK_MODEL)
        _log.info("reranker loaded", extra={"path": settings.RERANK_MODEL})
    except Exception as exc:  # noqa: BLE001 - degrade to no-rerank rather than break search
        _log.warning("reranker unavailable, continuing without it: %s", exc)
        _model = None
    return _model


def warmup() -> None:
    """Load the model at startup so the first search doesn't pay the download/init cost."""
    _get_model()


def rerank(query: str, documents: list[str]) -> list[float] | None:
    """Relevance score per document for the query, or None when reranking is off/unavailable."""
    model = _get_model()
    if model is None or not documents:
        return None
    try:
        return list(model.rerank(query, documents))
    except Exception as exc:  # noqa: BLE001
        _log.warning("rerank failed, keeping first-stage order: %s", exc)
        return None
