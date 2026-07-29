"""Repo-seeded system instructions: the always-injected 'how to work with HiveMind' memory
is maintained in the repo and upserted per org — idempotent, and it adopts a pre-existing
hand-made system node with the same title instead of duplicating it."""
from __future__ import annotations

from src.repository import graph_repo
from src.components import seed as seed_service


def _count_with_title(graph, org_uid, title):
    return graph.run(
        "MATCH (n:Knowledge {org_uid: $o, title: $t}) RETURN count(n) AS c",
        o=org_uid, t=title,
    ).single()["c"]


def test_seed_creates_system_memory(graph, org, account):
    title, content = seed_service.load_seed()
    assert title and "hive_update" in content  # the repo file drives the content

    seed_service.seed_org(graph, org["org_uid"])

    me = account("nick", role="member")
    system = graph_repo.list_system(graph, me)
    hit = next((n for n in system if n["title"] == title), None)
    assert hit is not None and hit["system"] is True
    assert hit["content"] == content


def test_seed_is_idempotent(graph, org):
    title, _ = seed_service.load_seed()
    seed_service.seed_org(graph, org["org_uid"])
    seed_service.seed_org(graph, org["org_uid"])
    assert _count_with_title(graph, org["org_uid"], title) == 1


def test_seed_adopts_handmade_node(graph, org, account):
    title, _ = seed_service.load_seed()
    # a legacy hand-made system node with the same title, no seed_key
    graph.run(
        """
        CREATE (n:Knowledge:Convention {uid: randomUUID(), org_uid: $o, type: 'convention',
            title: $t, content: 'oude handgemaakte tekst', scope: 'org', system: true,
            archived: false, created: timestamp(), last_used: timestamp(), use_count: 0})
        """,
        o=org["org_uid"], t=title,
    )
    seed_service.seed_org(graph, org["org_uid"])

    # adopted + refreshed, not duplicated
    assert _count_with_title(graph, org["org_uid"], title) == 1
    me = account("nick", role="member")
    hit = next(n for n in graph_repo.list_system(graph, me) if n["title"] == title)
    assert hit["content"] != "oude handgemaakte tekst"
