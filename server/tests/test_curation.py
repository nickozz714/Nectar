"""Topic creation, re-hanging nodes between topics, and tags (incl. tag-aware search)."""
from __future__ import annotations

import pytest

from src.repository import graph_repo
from src.services import curation_service, memory_service, search_service


def _mem(graph, acc, title, content, topics, tags=None):
    return memory_service.remember(graph, acc, "memory", title, content, topics,
                                   scope="org", tags=tags)


def test_create_topic_and_nest(graph, account):
    acc = account("nick", role="member")
    parent = curation_service.create_topic(graph, acc, "Data Modelling")
    child = curation_service.create_topic(graph, acc, "Gemeentelijk Gegevens Model (GGM)",
                                          parent_topic="Data Modelling")
    node = graph_repo.get_node(graph, acc, child["uid"])
    assert node["type"] == "topic"
    assert any(p["title"] == "Data Modelling" for p in node["parents"])
    # same title reuses the topic, no duplicate
    again = curation_service.create_topic(graph, acc, "Data Modelling")
    assert again["uid"] == parent["uid"]


def test_move_node_reparents(graph, account):
    maint = account("nick", role="maintainer")
    res = _mem(graph, maint, "GGM export werkwijze voorbeeld",
               "Hoe je de GGM export uitvoert vanaf de generator.", ["Gemeente Krimpenerwaard"])
    curation_service.move_node(graph, maint, res["uid"], "Gemeentelijk Gegevens Model (GGM)")
    parents = {p["title"] for p in graph_repo.get_node(graph, maint, res["uid"])["parents"]}
    assert parents == {"Gemeentelijk Gegevens Model (GGM)"}  # old parent replaced


def test_move_node_keep_others_multiparent(graph, account):
    maint = account("nick", role="maintainer")
    res = _mem(graph, maint, "Nog een GGM werkwijze om te verplaatsen",
               "Werkwijze die onder twee topics mag hangen.", ["Gemeente Krimpenerwaard"])
    curation_service.move_node(graph, maint, res["uid"], "GGM", keep_others=True)
    parents = {p["title"] for p in graph_repo.get_node(graph, maint, res["uid"])["parents"]}
    assert parents == {"Gemeente Krimpenerwaard", "GGM"}


def test_move_requires_maintainer(graph, account):
    member = account("mila", role="member")
    res = _mem(graph, member, "Werkwijze die een member niet mag verhangen",
               "Content lang genoeg voor de write-gate hier.", ["Swinkels"])
    with pytest.raises(ValueError, match="maintainer"):
        curation_service.move_node(graph, member, res["uid"], "Ander topic")


def test_tags_set_and_search(graph, account):
    acc = account("nick", role="member")
    res = _mem(graph, acc, "Fabric deployment met blue-green aanpak",
               "Uitleg over de blue-green deployment op Fabric.", ["Fabric werkwijzen"],
               tags=["deployment", "fabric"])
    node = graph_repo.get_node(graph, acc, res["uid"])
    assert set(node["tags"]) == {"deployment", "fabric"}

    # a query mentioning the tag boosts it; tag filter restricts
    hits = search_service.search(graph, acc, "iets over deployment", touch=False)
    assert any(h["uid"] == res["uid"] for h in hits)
    filtered = search_service.search(graph, acc, "willekeurig", touch=False, tags=["fabric"])
    assert all("fabric" in (h.get("tags") or []) for h in filtered)
    assert any(h["uid"] == res["uid"] for h in filtered)

    curation_service.set_tags(graph, acc, res["uid"], remove=["fabric"], add=["azure"])
    assert set(graph_repo.get_node(graph, acc, res["uid"])["tags"]) == {"deployment", "azure"}


def test_reclassify_sensitivity_fixes_false_positives(graph, account):
    admin = account("nick", role="org_admin")
    # simulate a node mislabeled by the old keyword classifier
    fp = _mem(graph, admin, "fastmcp Authorization-header valkuil",
              "get_http_headers() gaf de Authorization-header niet terug; lees via get_http_request(). Bearer-auth per tool-call.",
              ["HiveMind"])
    graph_repo.set_sensitivity(graph, fp["uid"], "gevoelig")  # old false positive
    real = _mem(graph, admin, "Voorbeeld met echte sleutel erin",
                "let op: api_key = ABCDEF0123456789 staat hier per ongeluk in de tekst.", ["HiveMind"])

    out = curation_service.reclassify_sensitivity(graph, admin)
    assert out["changed"] >= 1
    assert graph_repo.get_node(graph, admin, fp["uid"])["sensitivity"] == "intern"
    assert graph_repo.get_node(graph, admin, real["uid"])["sensitivity"] == "gevoelig"


def test_merge_topics(graph, account):
    maint = account("nick", role="maintainer")
    a = _mem(graph, maint, "GGM export werkwijze onder korte naam",
             "Werkwijze die onder het korte GGM-topic hangt.", ["GGM"])
    b = _mem(graph, maint, "GGM graaf werkwijze onder lange naam",
             "Werkwijze die onder het lange GGM-topic hangt.", ["Gemeentelijk Gegevens Model (GGM)"])

    out = curation_service.merge_topics(graph, maint, "GGM", "Gemeentelijk Gegevens Model (GGM)")
    assert out["moved_children"] == 1
    # the short topic is gone; both nodes now hang under the long one
    assert graph_repo.get_topic_by_title(graph, maint.org_uid, "GGM") is None
    for res in (a, b):
        parents = {p["title"] for p in graph_repo.get_node(graph, maint, res["uid"])["parents"]}
        assert "Gemeentelijk Gegevens Model (GGM)" in parents


def test_bulk_tags_and_nodes_brief(graph, account):
    maint = account("nick", role="maintainer")
    a = _mem(graph, maint, "Eerste node om in bulk te taggen",
             "Inhoud lang genoeg voor de write-gate hier.", ["Swinkels"])
    b = _mem(graph, maint, "Tweede node om in bulk te taggen",
             "Nog wat inhoud die lang genoeg is voor de gate.", ["Fabric werkwijzen"])

    brief = curation_service.list_nodes_brief(graph, maint)
    assert {n["uid"] for n in (a, b)}.issubset({n["uid"] for n in brief})
    assert all("topics" in n for n in brief)

    out = curation_service.bulk_set_tags(graph, maint, [
        {"uid": a["uid"], "tags": ["swinkels", "fabric"]},
        {"uid": b["uid"], "tags": ["fabric"]},
    ])
    assert out["updated"] == 2
    assert set(graph_repo.get_node(graph, maint, a["uid"])["tags"]) == {"swinkels", "fabric"}
