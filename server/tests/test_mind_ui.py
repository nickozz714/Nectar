"""De 3D-mind: de /graph/full-voeding en de pagina's. Er is nog maar één GUI —
de keuze tussen twee interfaces (default_ui) bestaat sinds 2026-09-09 niet meer."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import memory_service

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


def test_ui_mind_pages_served(client):
    r = client.get("/ui/mind")
    assert r.status_code == 200 and "mind.bundle.js" in r.text
    r = client.get("/ui/cockpit")
    assert r.status_code == 200 and "cockpit.bundle.js" in r.text
    assert client.get("/ui/mind.bundle.js").status_code == 200
    assert client.get("/ui/cockpit.bundle.js").status_code == 200


def test_er_is_maar_een_gui(client):
    """/ui is de mind — niet een tweede, oudere pagina ernaast.

    Dit is een afspraak die al een keer is teruggeslopen: er stonden twee
    interfaces naast elkaar, elk scherm moest twee keer gebouwd en gerepareerd
    worden, en /ui bleef de oude tonen. Deze test houdt dat tegen."""
    ui, mind = client.get("/ui"), client.get("/ui/mind")
    assert ui.status_code == 200
    assert ui.text == mind.text, "/ui moet exact dezelfde pagina zijn als /ui/mind"
    # de oude GUI en zijn bundel bestaan niet meer
    assert "graph.js" not in ui.text and "NectarGraph" not in ui.text
    assert client.get("/ui/assets/graph.js").status_code == 404
