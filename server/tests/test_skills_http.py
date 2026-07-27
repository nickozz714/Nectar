"""HTTP access to shared skills — the transport the installer/helper uses to load a skill
into a project's .claude/skills/ without needing the MCP connection."""
from __future__ import annotations


def _token_for(graph, account_obj):
    from src.repository import tenancy_repo

    return tenancy_repo.create_token(graph, account_obj.uid, "test", None,
                                     role=account_obj.role)["token"]


def test_list_and_get_skill_over_http(client, graph, account):
    from src.services import skill_service

    admin = account("nick", role="org_admin")
    files = [{"path": "SKILL.md", "content": "# Demo\nDo the thing."},
             {"path": "resources/helper.py", "content": "print('hi')"}]
    put = skill_service.put_skill(graph, admin, "Demo Skill", "A demo", files, [], scope="org")
    uid = put["uid"]
    headers = {"Authorization": f"Bearer {_token_for(graph, admin)}"}

    listing = client.get("/skills", headers=headers).json()
    assert any(s["uid"] == uid and s["title"] == "Demo Skill" for s in listing)

    got = client.get(f"/skills/{uid}", headers=headers)
    assert got.status_code == 200
    body = got.json()
    assert body["title"] == "Demo Skill"
    paths = {f["path"]: f["content"] for f in body["files"]}
    assert paths["SKILL.md"].startswith("# Demo")
    assert paths["resources/helper.py"] == "print('hi')"


def test_get_non_skill_returns_404(client, graph, account):
    from src.services import memory_service

    admin = account("nick", role="org_admin")
    mem = memory_service.remember(graph, admin, "memory", "Some memory title here",
                                  "body content long enough to pass the gate", [])
    headers = {"Authorization": f"Bearer {_token_for(graph, admin)}"}

    # a memory uid is not a skill -> 404
    assert client.get(f"/skills/{mem['uid']}", headers=headers).status_code == 404
    assert client.get("/skills/does-not-exist", headers=headers).status_code == 404


def test_skills_requires_auth(client):
    # no bearer at all -> rejected (422 missing header); a bogus bearer -> 401
    assert client.get("/skills").status_code in (401, 403, 422)
    assert client.get("/skills", headers={"Authorization": "Bearer nope"}).status_code == 401
