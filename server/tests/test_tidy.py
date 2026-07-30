"""Tidy scan: file loose knowledge under the nearest topic via safe promotion chores."""
from __future__ import annotations

from src.services import curation_service, memory_service


def _mem(graph, acc, title, content, topics):
    return memory_service.remember(graph, acc, "memory", title, content, topics, scope="org")


def test_tidy_scan_opens_promotion_for_homeless(graph, account):
    acc = account("nick", role="org_admin")
    curation_service.create_topic(graph, acc, "Fabric bronze ingestion")
    _mem(graph, acc, "Fabric bronze ingestion recept",
         "Hoe je een bronze ingestion in Fabric opzet met metadata en pipelines.", [])
    res = curation_service.tidy_scan(graph, acc)
    assert res["homeless"] >= 1
    assert any(c["target"] == "Fabric bronze ingestion" for c in res["chores"])
    assert all(c["status"] == "open" for c in res["chores"])   # 1 vote, needs org_admin resolve


def test_tidy_scan_idempotent(graph, account):
    acc = account("nick", role="org_admin")
    curation_service.create_topic(graph, acc, "Fabric bronze ingestion")
    _mem(graph, acc, "Fabric bronze ingestion recept",
         "Hoe je een bronze ingestion in Fabric opzet met metadata en pipelines.", [])
    first = curation_service.tidy_scan(graph, acc)["homeless"]
    # same suggestion_key → re-scan does not multiply chores in the hive
    curation_service.tidy_scan(graph, acc)
    from src.repository import governance_repo
    opens = governance_repo.chores_by_status(graph, acc.org_uid, "open")
    assert len([c for c in opens if c["type"] == "promotion"]) == first


def test_tidy_scan_skips_filed_nodes(graph, account):
    acc = account("nick", role="org_admin")
    _mem(graph, acc, "Netjes gearchiveerde memory",
         "Deze memory hangt al keurig onder een echt topic, geen chore nodig.", ["Netjes Topic"])
    res = curation_service.tidy_scan(graph, acc)
    assert all(c["node"] != "Netjes gearchiveerde memory" for c in res["chores"])
