"""Username + password login: set password, log in, get a working token."""
from __future__ import annotations


def _bootstrap(client, admin_headers, name="nick", role="org_admin"):
    org = client.post("/admin/orgs", json={"name": f"Org-{name}"}, headers=admin_headers).json()
    acc = client.post("/admin/accounts", headers=admin_headers,
                      json={"org_uid": org["uid"], "name": name, "role": role}).json()
    tok = client.post("/admin/tokens", headers=admin_headers,
                      json={"account_uid": acc["uid"]}).json()["token"]
    return org, acc, tok


def test_set_password_then_login(client, admin_headers):
    _, acc, token = _bootstrap(client, admin_headers, "nick")
    # set own password (authenticated with the token)
    r = client.post("/auth/password", json={"password": "geheim-wachtwoord"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # log in with username + password -> get a token
    r = client.post("/auth/login", json={"name": "nick", "password": "geheim-wachtwoord"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["role"] == "org_admin"

    # that token works
    me = client.get("/graph/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["name"] == "nick"


def test_wrong_password_rejected(client, admin_headers):
    _, _, token = _bootstrap(client, admin_headers, "nick")
    client.post("/auth/password", json={"password": "geheim-wachtwoord"},
                headers={"Authorization": f"Bearer {token}"})
    assert client.post("/auth/login", json={"name": "nick", "password": "fout"}).status_code == 401
    assert client.post("/auth/login", json={"name": "onbekend", "password": "x"}).status_code == 401


def test_password_too_short(client, admin_headers):
    _, _, token = _bootstrap(client, admin_headers, "nick")
    r = client.post("/auth/password", json={"password": "kort"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_login_without_password_set_fails(client, admin_headers):
    _bootstrap(client, admin_headers, "nick")  # no password set
    assert client.post("/auth/login", json={"name": "nick", "password": "whatever"}).status_code == 401


def test_org_admin_sets_password_for_other(client, admin_headers):
    org, _, admin_token = _bootstrap(client, admin_headers, "nick", "org_admin")
    client.post("/admin/accounts", headers=admin_headers,
                json={"org_uid": org["uid"], "name": "collega", "role": "member"})
    r = client.post("/auth/password/for", json={"name": "collega", "password": "collega-geheim"},
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert client.post("/auth/login", json={"name": "collega", "password": "collega-geheim"}).status_code == 200
