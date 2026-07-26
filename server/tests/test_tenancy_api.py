"""Tenancy, auth and roles over the REST surface."""
from __future__ import annotations


def _bootstrap(client, admin_headers, role="member"):
    org = client.post("/admin/orgs", json={"name": f"Acme-{role}"}, headers=admin_headers).json()
    acc = client.post("/admin/accounts", headers=admin_headers, json={
        "org_uid": org["uid"], "name": f"user-{role}", "role": role, "person": "Alice"}).json()
    tok = client.post("/admin/tokens", headers=admin_headers,
                      json={"account_uid": acc["uid"], "label": "laptop"}).json()
    return org, acc, tok["token"]


def test_bootstrap_and_person(client, admin_headers):
    org, acc, token = _bootstrap(client, admin_headers)
    assert acc["person"] == "Alice"
    assert token
    orgs = client.get("/admin/orgs", headers=admin_headers).json()
    assert any(o["uid"] == org["uid"] and o["accounts"] == 1 for o in orgs)


def test_admin_token_required(client):
    r = client.post("/admin/orgs", json={"name": "x"},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 403


def test_account_token_gates_recall(client, admin_headers):
    _, _, token = _bootstrap(client, admin_headers)
    assert client.post("/recall", json={"query": "x"},
                       headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/recall", json={"query": "x"},
                       headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_role_gate_on_review_queue(client, admin_headers):
    _, _, member = _bootstrap(client, admin_headers, role="member")
    _, _, admin = _bootstrap(client, admin_headers, role="org_admin")
    assert client.get("/review/chores",
                      headers={"Authorization": f"Bearer {member}"}).status_code == 403
    assert client.get("/review/chores",
                      headers={"Authorization": f"Bearer {admin}"}).status_code == 200


def test_token_rotate_revokes_old(client, admin_headers):
    org, acc, token = _bootstrap(client, admin_headers)
    tokens = client.get(f"/admin/accounts/{acc['uid']}/tokens", headers=admin_headers).json()
    old_hash = tokens[0]["hash"]
    rotated = client.post(f"/admin/tokens/{old_hash}/rotate", headers=admin_headers).json()
    assert rotated["token"] and rotated["token"] != token
    # old token dead, new token alive
    assert client.post("/recall", json={"query": "x"},
                       headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/recall", json={"query": "x"},
                       headers={"Authorization": f"Bearer {rotated['token']}"}).status_code == 200


def test_token_cleanup(client, admin_headers):
    org, acc, _ = _bootstrap(client, admin_headers)
    tokens = client.get(f"/admin/accounts/{acc['uid']}/tokens", headers=admin_headers).json()
    client.post(f"/admin/tokens/{tokens[0]['hash']}/revoke", headers=admin_headers)
    removed = client.post(f"/admin/tokens/cleanup?org_uid={org['uid']}",
                          headers=admin_headers).json()["removed"]
    assert removed >= 1
