"""Link prediction: propose RELATES between shared-neighbour, similar memories as Pollen."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import curation_service, governance_service, memory_service, org_service


def _mem(graph, acc, title, content):
    return memory_service.remember(graph, acc, "memory", title, content, ["T1", "T2"],
                                   scope="org", force=True)


def test_linkpred_proposes_and_apply_links(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    a = _mem(graph, admin, "Werkwijze tool Omega configureren en draaien deel een",
             "Een werkwijze over tool Omega configureren en draaien in projecten hier.")
    b = _mem(graph, admin, "Werkwijze tool Omega configureren en draaien deel twee",
             "Een werkwijze over tool Omega configureren en draaien in projecten daar.")
    # a and b share two common neighbours (topics T1, T2) and are semantically similar,
    # but are not directly linked → a RELATES suggestion should be proposed.
    res = curation_service.link_prediction_scan(graph, admin)
    assert res["opened"] >= 1
    chore = res["suggestions"][0]["chore"]

    governance_service.admin_resolve(graph, admin, chore, "apply", "ok")
    related = {r["uid"] for r in graph_repo.get_node(graph, admin, a["uid"])["related"]}
    assert b["uid"] in related   # now linked as related


def test_linkpred_no_candidates_is_safe(graph, account):
    admin = account("nick", role="maintainer")
    assert curation_service.link_prediction_scan(graph, admin)["opened"] == 0
