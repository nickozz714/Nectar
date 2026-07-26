"""org_admin hard-delete: the escape hatch from consensus-gated mutation."""
from __future__ import annotations

import pytest

from src.repository import graph_repo
from src.services import governance_service, memory_service


def _mem(graph, acc, title, content, topics):
    return memory_service.remember(graph, acc, "memory", title, content, topics, scope="org")


def test_org_admin_deletes_node(graph, account):
    admin = account("nick", role="org_admin")
    node = _mem(graph, admin, "Weg te gooien memory over iets", "Inhoud die ruimschoots lang genoeg is voor de kwaliteitspoort van de write-gate.", ["T"])
    res = governance_service.admin_delete(graph, admin, node["uid"])
    assert res["deleted"] is True
    assert graph_repo.get_node(graph, admin, node["uid"]) is None


def test_member_cannot_delete(graph, account):
    admin = account("nick", role="org_admin")
    member = account("collega", role="member")
    node = _mem(graph, admin, "Beschermde memory blijft staan", "Inhoud die ruimschoots lang genoeg is voor de kwaliteitspoort van de write-gate.", ["T"])
    with pytest.raises(ValueError, match="org_admin"):
        governance_service.admin_delete(graph, member, node["uid"])
    assert graph_repo.get_node(graph, admin, node["uid"]) is not None


def test_delete_unknown_node(graph, account):
    admin = account("nick", role="org_admin")
    with pytest.raises(ValueError, match="not found"):
        governance_service.admin_delete(graph, admin, "bestaat-niet")


def test_delete_removes_files_and_chores(graph, account):
    from src.services import skill_service

    admin = account("nick", role="org_admin")
    other = account("collega", role="maintainer")
    skill = skill_service.put_skill(graph, admin, "weg-skill", "beschrijving",
                                    [{"path": "SKILL.md", "content": "inhoud van de skill hier"}],
                                    ["T"], scope="org")
    # file a chore about it so we can confirm it's cleaned up too
    governance_service.suggest(graph, other, "invalidate", skill["uid"], {}, "oud", "m-a")
    governance_service.admin_delete(graph, admin, skill["uid"])
    assert graph_repo.get_node(graph, admin, skill["uid"]) is None
    # no dangling SkillFile / Chore referencing it
    assert graph.run("MATCH (f:SkillFile) RETURN count(f) AS n").single()["n"] == 0
    assert graph.run("MATCH (c:Chore) RETURN count(c) AS n").single()["n"] == 0
