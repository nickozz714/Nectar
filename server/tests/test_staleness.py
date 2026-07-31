"""Staleness scan: stale-but-used knowledge becomes a review Pollen; apply refreshes it."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import curation_service, governance_service, memory_service, org_service


def test_staleness_opens_review_and_apply_refreshes(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    n = memory_service.remember(graph, admin, "memory", "Veelgebruikte oude werkwijze hier",
                                "Een werkwijze die vaak gebruikt is maar al lang niet herzien werd.",
                                ["T"], scope="org")
    # make it stale + used: old last_used, use_count high
    old_ts = "timestamp() - (200 * 86400000)"
    graph.run(f"MATCH (x:Knowledge {{uid:$u}}) SET x.use_count = 9, x.last_used = {old_ts}", u=n["uid"])

    scan = curation_service.staleness_scan(graph, admin)
    assert scan["stale"] >= 1 and scan["opened"] >= 1
    chore = next(c for c in scan["chores"] if c["node"] == "Veelgebruikte oude werkwijze hier")

    out = governance_service.admin_resolve(graph, admin, chore["chore"], "apply", "nog correct")
    assert out["status"] == "resolved"
    node = graph_repo.get_node(graph, admin, n["uid"])
    assert node["lifecycle"] == "validated"   # confirmed current


def test_fresh_node_not_flagged(graph, account):
    admin = account("nick", role="org_admin")
    memory_service.remember(graph, admin, "memory", "Verse werkwijze die net gemaakt is",
                            "Een verse werkwijze die net is aangemaakt en dus niet stale is.",
                            ["T"], scope="org")
    assert curation_service.staleness_scan(graph, admin)["opened"] == 0
