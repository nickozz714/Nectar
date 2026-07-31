"""Bloom lifecycle: new memories start 'captured'; swarm-review matures them; recall weights it."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import governance_service, memory_service, search_service


def _mem(graph, acc, title, content, topics=("T",)):
    return memory_service.remember(graph, acc, "memory", title, content, list(topics), scope="org")


def test_new_memory_starts_captured(graph, account):
    acc = account("nick", role="member")
    node = _mem(graph, acc, "Een vers vastgelegd weetje hierzo",
                "Inhoud die lang genoeg is voor de write-gate, echt waar wel.")
    assert graph_repo.get_node(graph, acc, node["uid"])["lifecycle"] == "captured"


def test_applying_promotion_validates(graph, account, org):
    admin = account("nick", role="org_admin")
    from src.services import curation_service, org_service
    org_service.set_consensus_threshold(graph, admin, 1)
    # a homeless node → tidy opens a promotion Pollen → apply it → node becomes validated
    curation_service.create_topic(graph, admin, "Doeltopic voor promotie hier")
    node = _mem(graph, admin, "Losse memory zonder topic voor promotie",
                "Deze memory hangt nergens onder en moet een huis krijgen straks.", topics=[])
    scan = curation_service.tidy_scan(graph, admin)
    chore = next(c for c in scan["chores"] if c["node"] == "Losse memory zonder topic voor promotie")
    governance_service.admin_resolve(graph, admin, chore["chore"], "apply", "ok")
    assert graph_repo.get_node(graph, admin, node["uid"])["lifecycle"] == "validated"


def test_recall_prefers_mature_over_captured(graph, account):
    acc = account("nick", role="maintainer")
    cap = _mem(graph, acc, "Onbevestigd idee over tool Gamma bouwen",
               "Een vers idee over tool Gamma dat nog niet bevestigd is door de swarm.")
    mat = _mem(graph, acc, "Rijpe werkwijze over tool Gamma bouwen",
               "Een beproefde werkwijze over tool Gamma die de swarm heeft gevalideerd.")
    graph_repo.set_lifecycle(graph, acc.org_uid, mat["uid"], "mature")
    hits = search_service.search(graph, acc, "tool Gamma bouwen werkwijze idee", limit=10, touch=False)
    order = [n["uid"] for n in hits]
    assert order.index(mat["uid"]) < order.index(cap["uid"])
