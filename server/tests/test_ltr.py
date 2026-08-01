"""Learning-to-rank: feedback → labeled examples → trained weights → served ranking."""
from __future__ import annotations

import json

from src.repository import graph_repo
from src.services import ltr_service, memory_service, search_service

KEYS = search_service.FEATURE_KEYS


def _mem(graph, acc, title):
    return memory_service.remember(graph, acc, "memory", title,
                                   "Inhoud die lang genoeg is voor de write-gate, echt waar wel.",
                                   ["T"], scope="org", force=True)


def test_feedback_captures_labeled_example(graph, account):
    acc = account("nick", role="member")
    n = _mem(graph, acc, "Node voor een LTR-voorbeeld hierzo")
    graph_repo.record_impressions(graph, acc.org_uid,
                                  [{"uid": n["uid"], "features": {k: 0.5 for k in KEYS}}])
    graph_repo.record_feedback(graph, acc.org_uid, n["uid"], True)
    ex = graph_repo.ranker_examples(graph, acc.org_uid)
    assert len(ex) == 1 and ex[0]["label"] == 1


def test_train_reports_cold_start(graph, account):
    acc = account("nick", role="maintainer")
    r = ltr_service.train(graph, acc)
    assert r["trained"] is False and "need" in r


def test_train_learns_and_serves(graph, account, monkeypatch):
    from src.components.config import get_settings
    monkeypatch.setattr(get_settings(), "LTR_MIN_EXAMPLES", 8)
    acc = account("nick", role="maintainer")
    # linearly separable: high pagerank helped, low pagerank did not
    for _ in range(6):
        graph.run("CREATE (:RankExample {org_uid:$o, features:$f, label:1, at:timestamp()})",
                  o=acc.org_uid, f=json.dumps({**{k: 0.0 for k in KEYS}, "pagerank": 1.0}))
        graph.run("CREATE (:RankExample {org_uid:$o, features:$f, label:0, at:timestamp()})",
                  o=acc.org_uid, f=json.dumps({**{k: 0.0 for k in KEYS}, "pagerank": 0.0}))
    r = ltr_service.train(graph, acc)
    assert r["trained"] and r["weights"]["pagerank"] > 0
    # search now serves the LEARNED weights, not the hand-tuned defaults
    w, b = search_service._ranker(graph, acc.org_uid)
    assert w["pagerank"] > 0
