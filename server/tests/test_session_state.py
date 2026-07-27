"""Per-account session snapshots (save/resume/handoff), bound to the account."""
from __future__ import annotations

from src.repository import session_repo


def test_save_and_resume(graph, account):
    acc = account("nick")
    session_repo.save(graph, acc, "swinkels-werk", "stap 3 van de deploy; TODO: rooktest")
    got = session_repo.get(graph, acc, "swinkels-werk")
    assert got["state"].startswith("stap 3")
    assert any(s["key"] == "swinkels-werk" for s in session_repo.list_for(graph, acc))


def test_overwrite_keeps_one(graph, account):
    acc = account("nick")
    session_repo.save(graph, acc, "x", "eerste")
    session_repo.save(graph, acc, "x", "tweede")
    assert session_repo.get(graph, acc, "x")["state"] == "tweede"
    assert len(session_repo.list_for(graph, acc)) == 1


def test_bound_to_account(graph, account):
    a = account("nick")
    b = account("collega")
    session_repo.save(graph, a, "mijn", "geheim werk")
    # a different account (different token) cannot see it
    assert session_repo.get(graph, b, "mijn") is None
    assert session_repo.list_for(graph, b) == []


def test_delete(graph, account):
    acc = account("nick")
    session_repo.save(graph, acc, "weg", "x")
    assert session_repo.delete(graph, acc, "weg") is True
    assert session_repo.get(graph, acc, "weg") is None


def test_entra_disabled_by_default(client):
    assert client.get("/auth/entra/status").json() == {"enabled": False}
    assert client.get("/auth/entra/login", follow_redirects=False).status_code == 404
