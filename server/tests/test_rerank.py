"""Cross-encoder rerank rewires the base relevance of the top-K candidates; safe no-op when off."""
from __future__ import annotations

from src.services import search_service


def test_rerank_is_noop_when_disabled():
    cands = [({"uid": "a", "title": "x", "content": "y"}, 0.9),
             ({"uid": "b", "title": "p", "content": "q"}, 0.8)]
    assert search_service._rerank("query", cands) == cands   # RERANK_ENABLED=false in tests


def test_rerank_reorders_head_by_cross_encoder(monkeypatch):
    from src.components.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "RERANK_ENABLED", True)
    monkeypatch.setattr(s, "RERANK_TOP_K", 3)
    # fake cross-encoder: high score only for the doc that truly matches
    monkeypatch.setattr(search_service.reranker, "rerank",
                        lambda q, docs: [1.0 if "match" in d else 0.0 for d in docs])
    cands = [({"uid": "a", "title": "nope", "content": ""}, 0.9),
             ({"uid": "b", "title": "match here", "content": ""}, 0.5),
             ({"uid": "c", "title": "nope2", "content": ""}, 0.4)]
    out = {n["uid"]: sc for n, sc in search_service._rerank("query", cands)}
    assert out["b"] == 1.0 and out["a"] < out["b"] and out["c"] < out["b"]


def test_rerank_falls_back_when_model_unavailable(monkeypatch):
    from src.components.config import get_settings
    monkeypatch.setattr(get_settings(), "RERANK_ENABLED", True)
    monkeypatch.setattr(search_service.reranker, "rerank", lambda q, docs: None)  # model unavailable
    cands = [({"uid": "a", "title": "x", "content": ""}, 0.9), ({"uid": "b", "title": "y", "content": ""}, 0.8)]
    assert search_service._rerank("query", cands) == cands   # keeps first-stage order
