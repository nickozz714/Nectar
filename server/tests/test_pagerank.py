"""In-app PageRank: central, well-connected knowledge gets a higher structural score + ranking."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import curation_service, memory_service


def _mem(graph, acc, title):
    return memory_service.remember(graph, acc, "memory", title,
                                   "Inhoud die lang genoeg is voor de write-gate, echt waar wel.",
                                   ["T"], scope="org", force=True)


def test_hub_gets_higher_pagerank(graph, account):
    acc = account("nick", role="maintainer")
    hub = _mem(graph, acc, "Centrale hub-memory met veel relaties")
    a = _mem(graph, acc, "Losse memory A aan de rand")
    b = _mem(graph, acc, "Losse memory B aan de rand")
    c = _mem(graph, acc, "Losse memory C aan de rand")
    for leaf in (a, b, c):
        graph_repo.link(graph, acc, hub["uid"], leaf["uid"], "relates")

    res = curation_service.pagerank_scan(graph, acc)
    assert res["nodes"] >= 4
    hub_pr = graph_repo.get_node(graph, acc, hub["uid"])["pagerank"]
    leaf_pr = graph_repo.get_node(graph, acc, a["uid"])["pagerank"]
    assert hub_pr > leaf_pr   # the hub is structurally more important


def test_pagerank_empty_graph_is_safe(graph, account):
    acc = account("nick", role="maintainer")
    assert curation_service.pagerank_scan(graph, acc)["nodes"] == 0
