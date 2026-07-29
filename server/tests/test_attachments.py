"""Attachments (central artifact storage) and learnings (high-priority child knowledge)."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import attachment_service, memory_service, search_service


def _mem(graph, acc, title, content, topics, type_="memory", parent_node=""):
    return memory_service.remember(graph, acc, type_, title, content, topics, scope="org",
                                   parent_node=parent_node)


def test_attach_download_list_delete(graph, account):
    acc = account("nick", role="maintainer")
    node = _mem(graph, acc, "Memory met een verwijzing naar een export",
                "Zie de bijgevoegde export-SQL voor de details.", ["Swinkels"])
    meta = attachment_service.save(graph, acc, node["uid"], "export.sql",
                                   "application/sql", b"SELECT 1;\n")
    assert meta["size"] == 10 and meta["filename"] == "export.sql"

    from src.repository import attachment_repo
    lst = attachment_repo.list_for(graph, acc, node["uid"])
    assert len(lst) == 1 and "data" not in lst[0]  # metadata only

    data, name, ct = attachment_service.load(graph, acc, meta["uid"])
    assert data == b"SELECT 1;\n" and name == "export.sql" and ct == "application/sql"

    assert attachment_service.remove(graph, acc, meta["uid"]) is True
    assert attachment_repo.list_for(graph, acc, node["uid"]) == []


def test_attach_to_topic(graph, account):
    from src.repository import attachment_repo
    from src.services import curation_service
    acc = account("nick", role="maintainer")
    topic = curation_service.create_topic(graph, acc, "GGM")
    meta = attachment_service.save(graph, acc, topic["uid"], "diagram.png", "image/png", b"\x89PNG..")
    assert meta is not None
    assert len(attachment_repo.list_for(graph, acc, topic["uid"])) == 1


def test_attachment_size_cap(graph, account):
    import pytest
    from src.components.config import get_settings
    acc = account("nick", role="member")
    node = _mem(graph, acc, "Node voor de groottetest hierzo",
                "Inhoud die zeker lang genoeg is voor de write-gate hier.", ["T"])
    big = b"x" * (get_settings().ATTACHMENT_MAX_MB * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="too large"):
        attachment_service.save(graph, acc, node["uid"], "big.bin", "application/octet-stream", big)


def test_learning_boost_and_parent_child(graph, account):
    acc = account("nick", role="member")
    base = _mem(graph, acc, "Werkwijze waar een les uit voortkwam",
                "Een proces dat we standaard volgen bij Swinkels-implementaties.",
                ["Swinkels"], type_="process")
    learning = _mem(graph, acc, "Les: draai altijd eerst een dry-run",
                    "We verloren tijd door meteen live te draaien; doe eerst een dry-run.",
                    [], type_="learning", parent_node=base["uid"])
    # learning hangs as a child of the process node
    children = {c["uid"] for c in graph_repo.get_node(graph, acc, base["uid"])["children"]}
    assert learning["uid"] in children

    # a learning outranks an ordinary memory of equal relevance (high boost)
    hits = search_service.search(graph, acc, "dry-run draaien", touch=False)
    assert hits and hits[0]["type"] == "learning"
