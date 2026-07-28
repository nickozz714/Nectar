"""Active focus: the current task/plan/guardrails, re-injected every prompt to keep long
sessions on course. One per account; its own label so it never leaks into shared recall."""
from __future__ import annotations

from src.repository import focus_repo
from src.services import search_service


def test_set_normalizes_first_step_current(graph, account):
    me = account("nick", role="member")
    f = focus_repo.set_focus(
        graph, me, "Migreer domein X",
        ["Ontdek resources", "Bouw pipeline", "Valideer"],
        ["Werk in de back-end via de API", "Front-end alleen voor stap 2"],
        "Alle tabellen geladen en gevalideerd",
    )
    assert f["goal"] == "Migreer domein X"
    assert [s["status"] for s in f["steps"]] == ["current", "open", "open"]
    assert len(f["guardrails"]) == 2


def test_advance_marks_done_and_promotes_next(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a", "b", "c"], None, "")

    f = focus_repo.advance_focus(graph, me, completed_step=1, note="a gedaan")
    assert [s["status"] for s in f["steps"]] == ["done", "current", "open"]
    assert f["notes"][-1] == "a gedaan"

    # advance by text
    f = focus_repo.advance_focus(graph, me, completed_step="b")
    assert [s["status"] for s in f["steps"]] == ["done", "done", "current"]


def test_focus_injected_into_recall(client, graph, account):
    from src.repository import tenancy_repo

    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Backend-migratie", ["stap 1", "stap 2"],
                         ["Niet in de front-end klooien"], "klaar als getest")
    token = tenancy_repo.create_token(graph, me.uid, "t", None, role="member")["token"]

    r = client.post("/recall", headers={"Authorization": f"Bearer {token}"},
                    json={"query": "iets", "anchors": []}).json()
    ctx = r["context"]
    assert "Actieve taak" in ctx and "Backend-migratie" in ctx
    assert "Niet in de front-end klooien" in ctx  # guardrail is present


def test_focus_is_scoped_per_project(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel A", ["a1"], None, "", project="proj-a")
    focus_repo.set_focus(graph, me, "Doel B", ["b1"], None, "", project="proj-b")

    assert focus_repo.get_focus(graph, me, "proj-a")["goal"] == "Doel A"
    assert focus_repo.get_focus(graph, me, "proj-b")["goal"] == "Doel B"
    assert focus_repo.get_focus(graph, me, "onbekend") is None
    assert {f["project"] for f in focus_repo.list_for(graph, me)} == {"proj-a", "proj-b"}


def test_recall_scopes_focus_by_project(client, graph, account):
    from src.repository import tenancy_repo
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Alleen in A", ["x"], None, "", project="proj-a")
    token = tenancy_repo.create_token(graph, me.uid, "t", None, role="member")["token"]
    h = {"Authorization": f"Bearer {token}"}

    in_a = client.post("/recall", headers=h, json={"query": "q", "project": "proj-a"}).json()["context"]
    in_b = client.post("/recall", headers=h, json={"query": "q", "project": "proj-b"}).json()["context"]
    assert "Alleen in A" in in_a
    assert "Alleen in A" not in in_b


def test_focus_http_endpoints(client, graph, account):
    from src.repository import tenancy_repo
    me = account("nick", role="member")
    token = tenancy_repo.create_token(graph, me.uid, "t", None, role="member")["token"]
    h = {"Authorization": f"Bearer {token}"}

    client.post("/focus", headers=h, json={"project": "p", "goal": "GUI-doel",
                "steps": ["s1", "s2"], "guardrails": ["regel"], "done_when": "af"})
    lst = client.get("/focus", headers=h).json()
    assert any(f["goal"] == "GUI-doel" and f["project"] == "p" for f in lst)

    adv = client.post("/focus/advance", headers=h, json={"project": "p", "completed_step": 1}).json()
    assert [s["status"] for s in adv["steps"]] == ["done", "current"]

    assert client.request("DELETE", "/focus", headers=h, params={"project": "p"}).json()["cleared"] is True
    assert client.get("/focus", headers=h).json() == []


def test_clear_removes_focus(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a"], None, "")
    assert focus_repo.clear_focus(graph, me) is True
    assert focus_repo.get_focus(graph, me) is None


def test_render_focus_shows_icons(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a", "b"], ["regel"], "done")
    focus_repo.advance_focus(graph, me, completed_step=1)
    text = search_service.render_focus(focus_repo.get_focus(graph, me))
    assert "✓ 1. a" in text and "▶ 2. b" in text and "regel" in text
