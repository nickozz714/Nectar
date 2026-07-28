"""Graph structure, consensus-gated mutations, roles, scope-widening human gate."""
from __future__ import annotations

import pytest

from src.services import governance_service, memory_service


def _mem(graph, acc, title, content, topics, type_="memory"):
    return memory_service.remember(graph, acc, type_, title, content, topics, scope="org")


def test_multi_parent(graph, account):
    acc = account()
    res = _mem(graph, acc, "Kennis onder twee onderwerpen tegelijk",
               "Deze memory hoort logisch onder twee verschillende topics samen.",
               ["Swinkels", "Fabric werkwijzen"])
    from src.repository import graph_repo
    node = graph_repo.get_node(graph, acc, res["uid"])
    assert {p["title"] for p in node["parents"]} == {"Swinkels", "Fabric werkwijzen"}


def test_promotion_consensus_and_role_gate(graph, account):
    author = account("nick", role="member")
    maint = account("collega", role="maintainer")
    node = _mem(graph, author, "Generieke deploy werkwijze voorbeeld",
                "Een werkwijze die breder toepasbaar blijkt dan alleen dit project.", ["Swinkels"])
    payload = {"target_topic": "Deploy werkwijzen"}

    v1 = governance_service.suggest(graph, author, "promotion", node["uid"], payload, "generiek", "m-a")
    assert v1["status"] == "open" and v1["votes"] == 1
    v2 = governance_service.suggest(graph, maint, "promotion", node["uid"], payload, "eens", "m-b")
    assert v2["status"] == "ready" and v2["votes"] == 2

    # member may not resolve
    with pytest.raises(ValueError, match="maintainer"):
        governance_service.resolve(graph, author, v2["uid"], "apply", "x")

    out = governance_service.resolve(graph, maint, v2["uid"], "apply", "ok")
    assert out["status"] == "resolved"

    from src.repository import graph_repo
    parents = {p["title"] for p in graph_repo.get_node(graph, author, node["uid"])["parents"]}
    assert parents == {"Swinkels", "Deploy werkwijzen"}


def test_scope_widening_needs_human(graph, account):
    a1 = account("nick", role="org_admin")
    a2 = account("collega", role="maintainer")
    node = _mem(graph, a1, "Kennis die mogelijk org-breed moet",
                "Iets dat wellicht voor de hele organisatie relevant is niet enkel dit team.", ["T"])
    payload = {"target_scope": "org"}
    governance_service.suggest(graph, a1, "scope_widening", node["uid"], payload, "breed", "m-a")
    s2 = governance_service.suggest(graph, a2, "scope_widening", node["uid"], payload, "eens", "m-b")
    assert s2["status"] == "awaiting_human"

    # swarm cannot resolve a scope-widening chore
    with pytest.raises(ValueError):
        governance_service.resolve(graph, a2, s2["uid"], "apply", "x")

    res = governance_service.approve_scope_widening(graph, s2["uid"], a1.org_uid, "akkoord",
                                                    reviewed_by="nick")
    assert res["scope"] == "org"


def test_resolved_chores_lists_handled(graph, account):
    from src.repository import governance_repo
    author = account("nick", role="member")
    maint = account("collega", role="maintainer")
    node = _mem(graph, author, "Nog een generieke werkwijze om te promoten",
                "Breed toepasbare werkwijze die na consensus gepromoot wordt.", ["Swinkels"])
    payload = {"target_topic": "Algemene werkwijzen"}
    governance_service.suggest(graph, author, "promotion", node["uid"], payload, "generiek", "m-a")
    ready = governance_service.suggest(graph, maint, "promotion", node["uid"], payload, "eens", "m-b")

    # before resolving: nothing handled yet
    assert governance_repo.resolved_chores(graph, maint) == []

    governance_service.resolve(graph, maint, ready["uid"], "apply", "prima gepromoot")
    done = governance_repo.resolved_chores(graph, maint)
    assert len(done) == 1
    assert done[0]["status"] == "resolved" and done[0]["resolution"] == "prima gepromoot"
    assert done[0]["node_title"].startswith("Nog een generieke")


def test_org_admin_direct_resolves_open_chore(graph, account):
    """A single 'open' chore (no consensus) can be resolved directly by an org_admin,
    bypassing the 2-vote gate. Members/maintainers cannot use the bypass."""
    from src.repository import governance_repo, graph_repo
    admin = account("nick", role="org_admin")
    maint = account("collega", role="maintainer")
    node = _mem(graph, admin, "Promoveer deze werkwijze direct als admin",
                "Werkwijze die als solo-admin zonder consensus gepromoot moet kunnen worden.", ["Swinkels"])
    payload = {"target_topic": "Directe werkwijzen"}

    s = governance_service.suggest(graph, admin, "promotion", node["uid"], payload, "want handig", "m-a")
    assert s["status"] == "open"  # only one vote, never ready

    # maintainer (not org_admin) may not use the bypass
    with pytest.raises(ValueError, match="org_admin"):
        governance_service.admin_resolve(graph, maint, s["uid"], "apply", "nee")

    out = governance_service.admin_resolve(graph, admin, s["uid"], "apply", "direct toegepast")
    assert out["status"] == "resolved"
    done = governance_repo.resolved_chores(graph, admin)
    assert any(d["uid"] == s["uid"] and d["resolution"] == "direct toegepast" for d in done)
    parents = {p["title"] for p in graph_repo.get_node(graph, admin, node["uid"])["parents"]}
    assert "Directe werkwijzen" in parents
