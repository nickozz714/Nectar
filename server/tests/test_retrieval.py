"""Hybrid RRF fusion + relevance-capped, position-aware recall ordering (pure logic)."""
from __future__ import annotations

from src.services import search_service


def test_rrf_fuse_ranks_shared_hits_higher():
    a = ({"uid": "a"}, 0.9)
    b = ({"uid": "b"}, 0.8)
    c = ({"uid": "c"}, 0.7)
    # 'a' appears top of both lists → should win; 'c' only in one list
    fused = search_service._rrf_fuse([[a, b], [a, c]])
    by = {n["uid"]: s for n, s in fused}
    assert by["a"] == 1.0                      # normalized top
    assert by["a"] > by["b"] and by["a"] > by["c"]
    assert set(by) == {"a", "b", "c"}          # union of both lists


def test_cap_and_order_caps_and_brackets(monkeypatch):
    from src.components.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "RECALL_MAX_MEMORIES", 5)
    monkeypatch.setattr(s, "RECALL_REL_FLOOR", 0.0)
    res = [{"uid": u, "_score": sc} for u, sc in
           [("r0", 1.0), ("r1", 0.9), ("r2", 0.8), ("r3", 0.7), ("r4", 0.6)]]
    out = [n["uid"] for n in search_service.cap_and_order(res)]
    assert out[0] == "r0" and out[-1] == "r1"   # strongest at both ends
    assert out == ["r0", "r2", "r4", "r3", "r1"]


def test_cap_and_order_relevance_floor_drops_weak_tail(monkeypatch):
    from src.components.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "RECALL_MAX_MEMORIES", 10)
    monkeypatch.setattr(s, "RECALL_REL_FLOOR", 0.5)
    res = [{"uid": "a", "_score": 1.0}, {"uid": "b", "_score": 0.6}, {"uid": "c", "_score": 0.2}]
    out = {n["uid"] for n in search_service.cap_and_order(res)}
    assert out == {"a", "b"}   # c (0.2 < 0.5*1.0) dropped
