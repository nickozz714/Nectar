"""The 3D 'mind' interface: /graph/full feed, /ui/mind pages, default_ui org setting."""
from __future__ import annotations

import pytest

from src.repository import graph_repo, tenancy_repo
from src.services import memory_service, org_service

CONTENT = "Inhoud die ruim lang genoeg is voor de write-gate van de hive, met context."


def test_full_graph_shape_and_links(graph, account):
    acc = account("nick")
    m = memory_service.remember(graph, acc, "memory", "Swinkels brouwt Bavaria bier",
                                CONTENT, ["Swinkels"], scope="org", force=True)
    g = graph_repo.full_graph(graph, acc)
    ids = {n["id"] for n in g["nodes"]}
    assert m["uid"] in ids
    topic = next(n for n in g["nodes"] if n["type"] == "topic" and n["title"] == "Swinkels")
    assert topic["children"] == 1
    assert {"source": topic["id"], "target": m["uid"], "rel": "CONTAINS"} in g["links"]
    # geen uid-veld lekken buiten 'id'; shape is precies wat de 3D-interface verwacht
    assert set(g["nodes"][0]) == {"id", "title", "type", "tags", "children",
                                  "use_count", "pagerank", "lifecycle", "scope"}


def test_full_graph_respects_scope(graph, account):
    writer = account("nick", team=True)
    memory_service.remember(graph, writer, "memory", "Team-geheim over project Orion",
                            CONTENT, ["Orion"], scope="account", force=True)
    other = account("bee", team=False)
    titles = {n["title"] for n in graph_repo.full_graph(graph, other)["nodes"]}
    assert "Team-geheim over project Orion" not in titles


def test_default_ui_setting(graph, account):
    admin = account("nick", role="org_admin")
    assert tenancy_repo.get_default_ui(graph, admin.org_uid) == "legacy"
    out = org_service.set_default_ui(graph, admin, "mind")
    assert out == {"default_ui": "mind"}
    assert tenancy_repo.get_default_ui(graph, admin.org_uid) == "mind"
    with pytest.raises(ValueError, match="legacy"):
        org_service.set_default_ui(graph, admin, "vr-bril")


def test_ui_mind_pages_served(client):
    r = client.get("/ui/mind")
    assert r.status_code == 200 and "mind.bundle.js" in r.text
    r = client.get("/ui/cockpit")
    assert r.status_code == 200 and "cockpit.bundle.js" in r.text
    assert client.get("/ui/mind.bundle.js").status_code == 200
    assert client.get("/ui/cockpit.bundle.js").status_code == 200
