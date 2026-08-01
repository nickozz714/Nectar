"""op_route think-Pollen: the swarm reconciles near-duplicates; producer≠reviewer safeguard."""
from __future__ import annotations

import pytest

from src.repository import graph_repo, governance_repo
from src.services import governance_service, memory_service


def _mem(graph, acc, title, content):
    return memory_service.remember(graph, acc, "memory", title, content, ["T"], scope="org", force=True)


def _think(graph, writer, new_uid, keep_uid):
    return governance_repo.create_think_pollen(
        graph, writer, new_uid, "op_route",
        {"duplicate_uid": keep_uid, "decisions": ["ADD", "UPDATE", "DELETE", "NOOP"]},
        idem_key=f"op_route:{new_uid}")


def test_think_pollen_is_ready_immediately(graph, account):
    w = account("nick", role="member")
    keep = _mem(graph, w, "Bestaand weetje over tool Zeta bouwen", "Inhoud die lang genoeg is voor de gate hier.")
    new = _mem(graph, w, "Nieuw bijna-dubbel over tool Zeta bouwen", "Andere inhoud die lang genoeg is voor de gate.")
    p = _think(graph, w, new["uid"], keep["uid"])
    assert p["status"] == "ready" and p["type"] == "op_route"


def test_producer_cannot_merge_but_peer_can(graph, account):
    w = account("nick", role="member")
    other = account("bee", role="member")
    keep = _mem(graph, w, "Bestaand weetje over tool Zeta bouwen", "Inhoud die lang genoeg is voor de gate hier.")
    new = _mem(graph, w, "Nieuw bijna-dubbel over tool Zeta bouwen", "Andere inhoud die lang genoeg is voor de gate.")
    p = _think(graph, w, new["uid"], keep["uid"])

    with pytest.raises(ValueError, match="producer"):
        governance_service.resolve_think(graph, w, p["uid"], "UPDATE",
                                         merged_content="De samengevoegde inhoud die lang genoeg is.")
    out = governance_service.resolve_think(graph, other, p["uid"], "UPDATE",
                                           merged_title="Samengevoegd tool Zeta bouwen",
                                           merged_content="De samengevoegde inhoud die lang genoeg is.")
    assert out["decision"] == "UPDATE"
    kept = graph_repo.get_node(graph, other, keep["uid"])
    assert kept["title"] == "Samengevoegd tool Zeta bouwen" and kept["lifecycle"] == "validated"
    assert graph_repo.get_node(graph, other, new["uid"])["lifecycle"] == "deprecated"


def test_delete_archives_new(graph, account):
    w = account("nick", role="member")
    other = account("bee", role="member")
    keep = _mem(graph, w, "Bestaand weetje over tool Omega", "Inhoud die lang genoeg is voor de gate hier.")
    new = _mem(graph, w, "Dubbel weetje over tool Omega", "Andere inhoud die lang genoeg is voor de gate.")
    p = _think(graph, w, new["uid"], keep["uid"])
    out = governance_service.resolve_think(graph, other, p["uid"], "DELETE")
    assert "archived" in out["result"]
    assert graph_repo.get_node(graph, other, new["uid"])["lifecycle"] == "deprecated"


def test_add_keeps_both_and_writer_allowed(graph, account):
    w = account("nick", role="member")
    keep = _mem(graph, w, "Weetje A over tool Sigma", "Inhoud die lang genoeg is voor de gate hier.")
    new = _mem(graph, w, "Weetje B over tool Sigma", "Andere inhoud die lang genoeg is voor de gate.")
    p = _think(graph, w, new["uid"], keep["uid"])
    out = governance_service.resolve_think(graph, w, p["uid"], "ADD")   # non-destructive, writer allowed
    assert out["decision"] == "ADD"
    assert graph_repo.get_node(graph, w, new["uid"]).get("lifecycle") != "deprecated"
