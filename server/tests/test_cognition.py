"""Cognition-Pollen: optional, swarm-native world research on new memories (docs/COGNITION.md)."""
from __future__ import annotations

import pytest

from src.components.config import get_settings
from src.repository import tenancy_repo
from src.services import governance_service, memory_service

CONTENT = "Inhoud die ruim lang genoeg is voor de write-gate van de hive, met wat context."


def _mem(graph, acc, title, tags=None, type_="memory"):
    return memory_service.remember(
        graph, acc, type_, title, CONTENT, ["T"], scope="org", force=True, tags=tags)


def _cognition_pollen(graph, node_uid):
    rows = graph.run(
        "MATCH (c:Pollen {type: 'cognition'})-[:ABOUT]->(n {uid: $u}) "
        "RETURN c.uid AS uid, c.status AS status, c.payload AS payload",
        u=node_uid,
    )
    return [dict(r) for r in rows]


def _org_pollen_count(graph, org_uid):
    r = graph.run(
        "MATCH (c:Pollen {type: 'cognition', org_uid: $o}) RETURN count(c) AS n", o=org_uid
    ).single()
    return r["n"]


def test_no_pollen_when_org_disabled(graph, account):
    acc = account("nick")
    m = _mem(graph, acc, "Memory over Swinkels en Bavaria migratie")
    assert _cognition_pollen(graph, m["uid"]) == []


def test_pollen_when_enabled_ready_and_idempotent(graph, account):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    m = _mem(graph, acc, "Memory over Swinkels en Bavaria migratie")
    pollen = _cognition_pollen(graph, m["uid"])
    assert len(pollen) == 1 and pollen[0]["status"] == "ready"
    assert '"round": 0' in pollen[0]["payload"] and '"max_depth"' in pollen[0]["payload"]
    # re-triggering the same node merges on the idem key — never a duplicate briefje
    memory_service._maybe_open_cognition_pollen(graph, acc, m["uid"], "memory", None)
    assert len(_cognition_pollen(graph, m["uid"])) == 1


def test_world_knowledge_tag_and_type_suppress_trigger(graph, account):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    tagged = _mem(graph, acc, "Swinkels Family Brewers is een brouwer", tags=["World-Knowledge"])
    assert _cognition_pollen(graph, tagged["uid"]) == []
    ref = _mem(graph, acc, "Handmatige glossary zonder research", type_="glossary")
    assert _cognition_pollen(graph, ref["uid"]) == []


def test_daily_cap_bounds_new_pollen(graph, account, monkeypatch):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    monkeypatch.setattr(get_settings(), "COGNITION_DAILY_CAP", 2)
    for i in range(3):
        _mem(graph, acc, f"Uniek weetje nummer {i} over systeem Alfa{i}")
    assert _org_pollen_count(graph, acc.org_uid) == 2


def test_resolve_files_budgeted_follow_up_and_depth_stops(graph, account):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    m = _mem(graph, acc, "Memory over Swinkels en Bavaria migratie")
    p0 = _cognition_pollen(graph, m["uid"])[0]
    # the research output itself (world-knowledge) opens no pollen of its own
    ref = _mem(graph, acc, "Swinkels Family Brewers, Nederlandse brouwer", tags=["world-knowledge"])
    assert _cognition_pollen(graph, ref["uid"]) == []

    out = governance_service.resolve_cognition(
        graph, acc, p0["uid"], "Swinkels en Bavaria opgezocht",
        created_uids=[ref["uid"]],
        follow_up=[{"node_uid": ref["uid"], "question": "Welke merken heeft Swinkels nog meer?"}],
    )
    assert out["status"] == "resolved" and out["round"] == 0
    assert len(out["follow_up_filed"]) == 1

    p1 = _cognition_pollen(graph, ref["uid"])[0]
    assert '"round": 1' in p1["payload"]
    # round 1 is the last round (max_depth 2): a further follow-up is refused, not filed
    out2 = governance_service.resolve_cognition(
        graph, acc, p1["uid"], "Merkenlijst opgezocht",
        follow_up=[{"node_uid": ref["uid"], "question": "En de historie van elk merk?"}],
    )
    assert out2["status"] == "resolved" and out2["follow_up_filed"] == []
    assert out2["follow_up_refused"] == 1

    with pytest.raises(ValueError, match="already handled"):
        governance_service.resolve_cognition(graph, acc, p1["uid"], "nogmaals")


def test_follow_up_refused_when_org_disabled_meanwhile(graph, account):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    m = _mem(graph, acc, "Memory over systeem Beta en leverancier Gamma")
    p0 = _cognition_pollen(graph, m["uid"])[0]
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, False)
    out = governance_service.resolve_cognition(
        graph, acc, p0["uid"], "onderzocht",
        follow_up=[{"node_uid": m["uid"], "question": "Wat is Gamma precies?"}],
    )
    assert out["follow_up_filed"] == [] and out["follow_up_refused"] == 1


def test_gui_apply_is_guarded_but_reject_dismisses(graph, account):
    acc = account("nick")
    tenancy_repo.set_cognition_enabled(graph, acc.org_uid, True)
    m = _mem(graph, acc, "Memory over platform Delta en dienst Epsilon")
    p0 = _cognition_pollen(graph, m["uid"])[0]
    with pytest.raises(ValueError, match="hive_resolve_cognition"):
        governance_service.resolve(graph, acc, p0["uid"], "apply", "")
    out = governance_service.resolve(graph, acc, p0["uid"], "reject", "niet nodig")
    assert out["status"] == "rejected"
