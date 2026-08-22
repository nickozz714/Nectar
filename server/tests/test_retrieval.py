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


# ---- Skills must be able to win a recall slot -------------------------------------------------
# The hive holds skills nobody could reach: a client discovers only its LOCAL skills, and in
# ranking a skill carried no boost while learnings did. Recall therefore kept offering the
# LESSONS about a way of working and never the way of working itself.

def _score(node: dict, sim: float = 0.8) -> float:
    import time
    weights, bias = search_service._default_weights()
    feat = search_service._features(node, sim, time.time() * 1000, set(), "")
    return search_service._apply(feat, weights, bias)


def test_skill_is_not_outranked_by_a_learning_at_equal_similarity():
    now = __import__("time").time() * 1000
    skill = {"uid": "s", "type": "skill", "last_used": now}
    learning = {"uid": "l", "type": "learning", "last_used": now}
    assert _score(skill) >= _score(learning)


def test_skill_beats_a_plain_memory_at_equal_similarity():
    now = __import__("time").time() * 1000
    assert _score({"uid": "s", "type": "skill", "last_used": now}) > \
           _score({"uid": "m", "type": "memory", "last_used": now})


def test_skill_does_not_rot_out_of_recall_while_unused():
    """A way of working stays valid however long ago it last ran; with the fast half-life a
    skill untouched for two months had decayed to a quarter and never surfaced again."""
    old = __import__("time").time() * 1000 - 60 * 86_400_000
    assert search_service._freshness({"type": "skill", "last_used": old},
                                     __import__("time").time() * 1000) > 0.8


def test_recall_tells_you_how_to_pull_a_surfaced_skill_in():
    """Surfacing it is half the job — the client still has to fetch it to use it."""
    out = search_service.render_results(
        [{"uid": "abc", "type": "skill", "title": "silver-validation", "content": "x", "topics": []}])
    assert "skill_get(\"abc\")" in out
    assert "niet lokaal geïnstalleerd" in out


def test_ordinary_memory_keeps_its_plain_one_line_rendering():
    out = search_service.render_results(
        [{"uid": "m1", "type": "memory", "title": "T", "content": "x", "topics": []}])
    assert out.count("\n") == 0 and "skill_get" not in out
