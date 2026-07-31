"""Importance pin + outcome-based 'Memory Worth' shift recall ranking."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import memory_service, search_service


def _mem(graph, acc, title, content):
    return memory_service.remember(graph, acc, "memory", title, content, ["Tools"], scope="org", force=True)


def test_importance_pin_reranks(graph, account):
    acc = account("nick", role="maintainer")
    a = _mem(graph, acc, "Werkwijze tool Delta bouwen stap een",
             "Een werkwijze over tool Delta bouwen die we vaak gebruiken hier zeker.")
    b = _mem(graph, acc, "Werkwijze tool Delta bouwen stap twee",
             "Een werkwijze over tool Delta bouwen die we vaak gebruiken hier zeker.")
    graph_repo.set_importance(graph, acc.org_uid, a["uid"], 0.9)
    graph_repo.set_importance(graph, acc.org_uid, b["uid"], 0.2)
    order = [n["uid"] for n in search_service.search(graph, acc, "werkwijze tool Delta bouwen", limit=10, touch=False)]
    assert order.index(a["uid"]) < order.index(b["uid"])


def test_outcome_worth_reranks(graph, account):
    acc = account("nick", role="member")
    good = _mem(graph, acc, "Aanpak tool Epsilon draaien variant een",
                "Een aanpak over tool Epsilon draaien die we toepassen in projecten hier.")
    bad = _mem(graph, acc, "Aanpak tool Epsilon draaien variant twee",
               "Een aanpak over tool Epsilon draaien die we toepassen in projecten hier.")
    for _ in range(3):
        graph_repo.record_feedback(graph, acc.org_uid, good["uid"], True)
        graph_repo.record_feedback(graph, acc.org_uid, bad["uid"], False)
    order = [n["uid"] for n in search_service.search(graph, acc, "aanpak tool Epsilon draaien", limit=10, touch=False)]
    assert order.index(good["uid"]) < order.index(bad["uid"])


def test_feedback_counters(graph, account):
    acc = account("nick", role="member")
    n = _mem(graph, acc, "Node voor feedback-telling hierzo",
             "Inhoud die lang genoeg is voor de write-gate, echt waar wel.")
    r1 = graph_repo.record_feedback(graph, acc.org_uid, n["uid"], True)
    r2 = graph_repo.record_feedback(graph, acc.org_uid, n["uid"], False)
    assert r1["pos"] == 1 and r2["neg"] == 1
