"""Bi-temporal supersession: a newer fact demotes the older one it replaces (never deletes)."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import memory_service, search_service


def _mem(graph, acc, title, content):
    return memory_service.remember(graph, acc, "decision", title, content, ["Tools"], scope="org")


def test_supersede_marks_and_demotes(graph, account):
    acc = account("nick", role="maintainer")
    old = _mem(graph, acc, "Besluit: we gebruiken tool Alpha voor de builds",
               "We kiezen tool Alpha als build-systeem voor alle projecten hier.")
    new = _mem(graph, acc, "Besluit: gemigreerd van Alpha naar tool Beta voor de builds",
               "We zijn gemigreerd naar tool Beta; Alpha wordt niet meer gebruikt voor builds.")

    res = graph_repo.supersede(graph, acc, old["uid"], new["uid"])
    assert res["new_uid"] == new["uid"] and res["old_uid"] == old["uid"]

    marked = graph_repo.get_node(graph, acc, old["uid"])
    assert marked["superseded_by"] == new["uid"] and marked.get("superseded_at")

    # both still findable, but the current truth outranks the superseded one
    hits = search_service.search(graph, acc, "besluit tool builds Alpha Beta", limit=10, touch=False)
    order = [n["uid"] for n in hits]
    assert new["uid"] in order and old["uid"] in order
    assert order.index(new["uid"]) < order.index(old["uid"])
