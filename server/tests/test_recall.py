"""Recall composition (shared by the HTTP hook and the client-agnostic hive_recall MCP tool)."""
from __future__ import annotations

from src.services import memory_service, recall_service


def test_recall_composes_ranked_context(graph, account):
    acc = account("nick", role="member")
    memory_service.remember(graph, acc, "memory", "Hoe je tool Kappa configureert hier",
                            "Stappen om tool Kappa correct te configureren in projecten.", ["T"], scope="org")
    r = recall_service.recall(graph, acc, "tool Kappa configureren", limit=5)
    assert r["result_count"] >= 1
    assert "Nectar recall" in r["context"] and "Kappa" in r["context"]
    assert "ready_chores" in r


def test_recall_empty_records_gap(graph, account):
    from src.repository import graph_repo
    acc = account("nick", role="member")
    recall_service.recall(graph, acc, "iets volstrekt onbekends qwerty zxcvb", limit=5)
    gaps = graph_repo.top_gaps(graph, acc.org_uid, 10)
    assert any("qwerty" in g["query"] for g in gaps)
