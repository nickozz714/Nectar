"""Contextual Pollen: hand each visiting model the one task most relevant to its prompt."""
from __future__ import annotations

from src.services import curation_service, governance_service, memory_service


def _mem(graph, acc, title, content, topics):
    return memory_service.remember(graph, acc, "memory", title, content, topics, scope="org")


def test_pick_contextual_pollen_matches_query(graph, account):
    acc = account("nick", role="org_admin")
    curation_service.create_topic(graph, acc, "Fabric bronze ingestion")
    _mem(graph, acc, "Fabric bronze ingestion recept",
         "Hoe je een bronze ingestion in Fabric opzet met metadata en pipelines.", [])
    # tidy scan opens a promotion Pollen about the homeless node
    assert curation_service.tidy_scan(graph, acc)["homeless"] >= 1

    hit = governance_service.pick_contextual_pollen(graph, acc, "fabric bronze ingestion metadata")
    assert hit is not None
    assert "Fabric bronze ingestion recept" == hit["node_title"]
    line = governance_service.render_pollen(hit)
    assert "Pollen" in line and hit["uid"] in line


def test_pick_contextual_pollen_none_when_empty(graph, account):
    acc = account("nick", role="org_admin")
    assert governance_service.pick_contextual_pollen(graph, acc, "wat dan ook") is None
