"""Active focus: the current task/plan/guardrails, re-injected every prompt to keep long
sessions on course. One per account + project + LANE (so parallel sessions each steer their own
task); its own node label so it never leaks into shared recall."""
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

    assert client.request("DELETE", "/focus", headers=h,
                          params={"project": "p", "lane": ""}).json()["cleared"] is True
    assert client.get("/focus", headers=h).json() == []


def test_clear_removes_focus(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a"], None, "")
    assert focus_repo.clear_focus(graph, me) == 1
    assert focus_repo.get_focus(graph, me) is None


def test_render_focus_shows_icons(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a", "b"], ["regel"], "done")
    focus_repo.advance_focus(graph, me, completed_step=1)
    text = search_service.render_focus(focus_repo.get_focus(graph, me))
    assert "✓ 1. a" in text and "▶ 2. b" in text and "regel" in text


# ─── Lanes: several sessions steering their own task in ONE project ──────────────────

def test_two_sessions_in_one_project_keep_own_focus(graph, account):
    me = account("nick", role="member")
    a = focus_repo.set_focus(graph, me, "Doel A", ["a1"], None, "",
                             project="p", session_id="aaaa1111-xxxx")
    b = focus_repo.set_focus(graph, me, "Doel B", ["b1"], None, "",
                             project="p", session_id="bbbb2222-yyyy")
    assert a["lane"] != b["lane"]

    # each session resolves to its OWN focus — no overwriting
    assert focus_repo.get_focus(graph, me, "p", session_id="aaaa1111-xxxx")["goal"] == "Doel A"
    assert focus_repo.get_focus(graph, me, "p", session_id="bbbb2222-yyyy")["goal"] == "Doel B"
    assert {f["goal"] for f in focus_repo.list_for(graph, me, project="p")} == {"Doel A", "Doel B"}


def test_same_session_updates_its_own_lane(graph, account):
    me = account("nick", role="member")
    sid = "aaaa1111-xxxx"
    focus_repo.set_focus(graph, me, "Doel A", ["a1", "a2"], None, "", project="p", session_id=sid)
    focus_repo.set_focus(graph, me, "Doel B", ["b1"], None, "", project="p", session_id="bbbb2222")

    f = focus_repo.advance_focus(graph, me, completed_step=1, note="a1 af",
                                 project="p", session_id=sid)
    assert f["goal"] == "Doel A" and [s["status"] for s in f["steps"]] == ["done", "current"]
    # the sibling lane is untouched
    other = focus_repo.get_focus(graph, me, "p", session_id="bbbb2222")
    assert other["goal"] == "Doel B" and other["steps"][0]["status"] == "current"

    # a second focus_set from the same session replaces its OWN lane, doesn't add one
    focus_repo.set_focus(graph, me, "Doel A2", ["x"], None, "", project="p", session_id=sid)
    assert len(focus_repo.list_for(graph, me, project="p")) == 2
    assert focus_repo.get_focus(graph, me, "p", session_id=sid)["goal"] == "Doel A2"


def test_named_lane_can_be_resumed_from_a_new_session(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Ollama", ["stap"], None, "", project="p",
                         session_id="old-session", name="Ollama migratie")
    lane = focus_repo.get_focus(graph, me, "p", session_id="old-session")["lane"]
    assert lane == "ollama-migratie"

    # a fresh session (after /clear) joins the named lane and sees the same task
    joined = focus_repo.get_focus(graph, me, "p", name="Ollama migratie")
    assert joined["goal"] == "Ollama"
    assert focus_repo.bind_session(graph, me, "p", lane, "new-session") is True
    assert focus_repo.get_focus(graph, me, "p", session_id="new-session")["goal"] == "Ollama"
    assert len(focus_repo.list_for(graph, me, project="p")) == 1  # still ONE lane


def test_session_without_lane_falls_back_to_project_focus(graph, account):
    """Clients that send no session id (or a brand-new session) see the project-wide focus —
    the original single-focus behaviour stays intact."""
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Project-breed", ["s"], None, "", project="p")

    assert focus_repo.get_focus(graph, me, "p")["goal"] == "Project-breed"
    assert focus_repo.get_focus(graph, me, "p", session_id="onbekend")["goal"] == "Project-breed"


def test_recall_gives_each_session_its_own_focus_and_lane_token(client, graph, account):
    from src.repository import tenancy_repo
    me = account("nick", role="member")
    token = tenancy_repo.create_token(graph, me.uid, "t", None, role="member")["token"]
    h = {"Authorization": f"Bearer {token}"}
    focus_repo.set_focus(graph, me, "Taak A", ["a1"], None, "", project="p",
                         session_id="aaaa1111-xx")
    focus_repo.set_focus(graph, me, "Taak B", ["b1"], None, "", project="p",
                         session_id="bbbb2222-yy")

    ctx_a = client.post("/recall", headers=h, json={"query": "q", "project": "p",
                                                   "session": "aaaa1111-xx"}).json()["context"]
    ctx_b = client.post("/recall", headers=h, json={"query": "q", "project": "p",
                                                   "session": "bbbb2222-yy"}).json()["context"]
    assert "Taak A" in ctx_a and "Taak B" not in ctx_a
    assert "Taak B" in ctx_b and "Taak A" not in ctx_b
    # the lane token is handed to the model so it keeps writing to its own lane
    assert 'session="aaaa1111"' in ctx_a
    assert 'session="bbbb2222"' in ctx_b

    # a session with no focus yet gets the hint to claim its own lane
    ctx_c = client.post("/recall", headers=h, json={"query": "q", "project": "p",
                                                   "session": "cccc3333-zz"}).json()["context"]
    assert "cccc3333" in ctx_c and "focus_set" in ctx_c


def test_clear_only_removes_own_lane(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "A", ["a"], None, "", project="p", session_id="aaaa1111")
    focus_repo.set_focus(graph, me, "B", ["b"], None, "", project="p", session_id="bbbb2222")

    assert focus_repo.clear_focus(graph, me, project="p", session_id="aaaa1111") == 1
    assert [f["goal"] for f in focus_repo.list_for(graph, me, project="p")] == ["B"]
    assert focus_repo.clear_focus(graph, me, project="p", all_lanes=True) == 1
    assert focus_repo.list_for(graph, me, project="p") == []


def test_prune_removes_stale_lanes_only(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Project-breed", ["a"], None, "", project="p")
    focus_repo.set_focus(graph, me, "Oude sessie", ["a"], None, "", project="p",
                         session_id="aaaa1111")
    focus_repo.set_focus(graph, me, "Verse sessie", ["a"], None, "", project="p",
                         session_id="bbbb2222")
    # age the first session lane past the cutoff
    graph.run("MATCH (f:HiveFocus {lane: 's-aaaa1111'}) SET f.last_seen = timestamp() - $ms",
              ms=focus_repo.STALE_LANE_DAYS * 86_400_000 + 1000)

    assert focus_repo.prune_stale(graph, me) == 1
    assert {f["goal"] for f in focus_repo.list_for(graph, me, project="p")} == {
        "Project-breed", "Verse sessie"}


def test_focus_http_lanes(client, graph, account):
    from src.repository import tenancy_repo
    me = account("nick", role="member")
    token = tenancy_repo.create_token(graph, me.uid, "t", None, role="member")["token"]
    h = {"Authorization": f"Bearer {token}"}

    client.post("/focus", headers=h, json={"project": "p", "goal": "Baan 1", "steps": ["s1"],
                                          "name": "baan een"})
    client.post("/focus", headers=h, json={"project": "p", "goal": "Baan 2", "steps": ["s1"],
                                          "session": "dddd4444"})
    lst = client.get("/focus", headers=h, params={"project": "p"}).json()
    assert {f["goal"] for f in lst} == {"Baan 1", "Baan 2"}
    assert {f["lane"] for f in lst} == {"baan-een", "s-dddd4444"}

    adv = client.post("/focus/advance", headers=h,
                      json={"project": "p", "lane": "baan-een", "completed_step": 1}).json()
    assert adv["goal"] == "Baan 1" and adv["steps"][0]["status"] == "done"

    assert client.request("DELETE", "/focus", headers=h,
                         params={"project": "p", "lane": "baan-een"}).json()["removed"] == 1
    assert client.request("DELETE", "/focus", headers=h,
                         params={"project": "p", "all_lanes": True}).json()["removed"] == 1


def test_render_focus_without_token_keeps_plain_hint(graph, account):
    me = account("nick", role="member")
    focus_repo.set_focus(graph, me, "Doel", ["a"], None, "")
    text = search_service.render_focus(focus_repo.get_focus(graph, me))
    assert "`focus_advance`" in text and "session=" not in text
