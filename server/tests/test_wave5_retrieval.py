"""Multi-hop retrieval expansion + stigmergy Pollen claims."""
from __future__ import annotations

from src.repository import graph_repo, governance_repo
from src.services import memory_service, search_service, governance_service, org_service


def _mem(graph, acc, title, content, topics=("T",)):
    return memory_service.remember(graph, acc, "memory", title, content, list(topics), scope="org", force=True)


def test_multihop_surfaces_a_neighbour(graph, account):
    acc = account("nick", role="maintainer")
    a = _mem(graph, acc, "Anchor over de zorgpad ingest pipeline",
             "Deze memory gaat over de zorgpad ingest pipeline en matcht de query.")
    b = _mem(graph, acc, "Losse notitie over een heel ander onderwerp konijnen",
             "Iets over konijnen en heuvels dat totaal niet op de query lijkt qua woorden.")
    graph_repo.link(graph, acc, a["uid"], b["uid"], "relates")   # b hangs one edge from a
    hits = [n["uid"] for n in search_service.search(graph, acc, "zorgpad ingest pipeline", limit=10, touch=False)]
    assert a["uid"] in hits and b["uid"] in hits   # b pulled in via multi-hop even though words differ


def test_claim_hides_pollen_from_other_agents(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    other = account("bee", role="member")
    node = _mem(graph, admin, "Node met een openstaande pollen taak hier",
                "Inhoud die lang genoeg is voor de write-gate, echt waar wel.")
    p = governance_service.suggest(graph, admin, "invalidate", node["uid"], {}, "weg", "m")

    assert governance_repo.claim_pollen(graph, admin.org_uid, p["uid"], admin.uid, 20) is not None
    # the other agent no longer sees this pollen among candidates
    mine = [c["uid"] for c in governance_repo.candidate_pollen(graph, admin, ttl_min=20)]
    theirs = [c["uid"] for c in governance_repo.candidate_pollen(graph, other, ttl_min=20)]
    assert p["uid"] in mine and p["uid"] not in theirs
    # a second agent cannot steal an active claim
    assert governance_repo.claim_pollen(graph, admin.org_uid, p["uid"], other.uid, 20) is None
    # release frees it
    assert governance_repo.release_pollen(graph, admin.org_uid, p["uid"], admin.uid) is True
    assert p["uid"] in [c["uid"] for c in governance_repo.candidate_pollen(graph, other, ttl_min=20)]
