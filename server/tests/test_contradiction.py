"""Contradiction detection: highly-similar memory pairs are surfaced as a contradiction-check
think-Pollen; the swarm judges 'compatible' (close) or 'contradiction' (supersede the outdated)."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import curation_service, governance_service, memory_service, org_service


def _mem(graph, acc, title, content):
    return memory_service.remember(graph, acc, "memory", title, content, ["Deploybeleid"],
                                   scope="org", force=True)


def test_contradiction_scan_files_pollen_and_supersedes(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    # Two memories on the same subject with an opposing value — similar wording (Neo4j cosine
    # score ~0.83, inside the [CONTRA_MIN_SIM, DEDUP) band), different truth.
    old = _mem(graph, admin, "Deploybeleid voor het uitrollen van de release naar productie omgeving",
               "Wij rollen handmatig uit via het dashboard elke maandag.")
    new = _mem(graph, admin, "Deploybeleid voor het uitrollen van de release naar productie omgeving",
               "Alles gaat nu automatisch via de pijplijn na elke merge.")

    res = curation_service.contradiction_scan(graph, admin)
    assert res["opened"] >= 1
    pair = next(p for p in res["pairs"])
    pollen_uid = pair["chore"]

    # Judge it a real contradiction: the Friday memory is the current truth, Monday is outdated.
    out = governance_service.resolve_contradiction(
        graph, admin, pollen_uid, "contradiction", current_uid=new["uid"], outdated_uid=old["uid"])
    assert out["status"] == "resolved"

    marked = graph_repo.get_node(graph, admin, old["uid"])
    assert marked["superseded_by"] == new["uid"]
    assert marked["lifecycle"] == "deprecated"


def test_contradiction_compatible_just_closes(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    # Two compatible facts on the same subject (Neo4j cosine score ~0.90, in-band) — no conflict.
    a = _mem(graph, admin, "Onboarding van een nieuwe medewerker binnen het ontwikkelteam hier",
             "Regel op dag een de toegang tot de gedeelde code repository.")
    b = _mem(graph, admin, "Onboarding van een nieuwe medewerker binnen het ontwikkelteam hier",
             "Regel op dag een een kennismaking met de directe collega's.")
    res = curation_service.contradiction_scan(graph, admin)
    assert res["opened"] >= 1
    pollen_uid = res["pairs"][0]["chore"]
    out = governance_service.resolve_contradiction(graph, admin, pollen_uid, "compatible")
    assert out["status"] == "resolved"
    # Neither node was superseded.
    assert not graph_repo.get_node(graph, admin, a["uid"]).get("superseded_by")
    assert not graph_repo.get_node(graph, admin, b["uid"]).get("superseded_by")


def test_contradiction_scan_no_pairs_is_safe(graph, account):
    admin = account("nick", role="maintainer")
    assert curation_service.contradiction_scan(graph, admin)["opened"] == 0


def _open_view(graph, admin, want_route):
    """Fetch the open Pollen and return the enriched view for the first of the wanted route."""
    from src.repository import governance_repo
    for c in governance_repo.open_chores(graph, admin, limit=25):
        v = governance_service.build_pollen_view(graph, admin, c)
        if v["route"] == want_route:
            return v
    return None


def test_pollen_view_is_human_readable_for_contradiction(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    _mem(graph, admin, "Deploybeleid voor het uitrollen van de release naar productie omgeving",
         "Wij rollen handmatig uit via het dashboard elke maandag.")
    _mem(graph, admin, "Deploybeleid voor het uitrollen van de release naar productie omgeving",
         "Alles gaat nu automatisch via de pijplijn na elke merge.")
    curation_service.contradiction_scan(graph, admin)

    v = _open_view(graph, admin, "contradiction")
    assert v is not None
    # Both memories carry real, readable text — not uids — and a plain-language explanation.
    assert "dashboard" in v["primary"]["content"] or "pijplijn" in v["primary"]["content"]
    assert v["compare"]["content"]
    assert v["explain"] and v["headline"]
    # Action refs exist for the buttons but are never part of the displayed text.
    assert v["refs"]["a"] and v["refs"]["b"]
    for field in (v["headline"], v["explain"], v["primary"]["title"], v["primary"]["content"]):
        assert v["refs"]["a"] not in field and v["refs"]["b"] not in field


def test_pollen_view_shows_before_and_after_for_edit(graph, account):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    m = _mem(graph, admin, "Vergaderritme van het team", "We vergaderen elke maandag om negen uur.")
    governance_service.suggest(graph, admin, "edit", m["uid"],
                               {"title": "Vergaderritme van het team",
                                "content": "We vergaderen voortaan elke vrijdag om vier uur."},
                               "geactualiseerd", "claude-fable-5")
    v = _open_view(graph, admin, "standard")
    # An edit surfaces the current text and the proposed text side by side.
    assert v is not None and v["proposed"] is not None
    assert "maandag" in v["primary"]["content"]
    assert "vrijdag" in v["proposed"]["content"]
