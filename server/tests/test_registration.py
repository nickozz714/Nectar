"""Self-registration (first-user bootstrap + invite-only), role-on-token, invites."""
from __future__ import annotations


def test_first_user_bootstraps_org_admin(client):
    status = client.get("/register").json()
    assert status["first_run"] is True

    r = client.post("/register", json={"name": "Alice", "email": "alice@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "org_admin" and body["token"]

    # the token works and carries org_admin (role bound to token)
    me = client.get("/graph/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["role"] == "org_admin" and me["can_review"] is True

    # no longer first run
    assert client.get("/register").json()["first_run"] is False


def test_registration_is_invite_only_after_first(client):
    client.post("/register", json={"name": "Alice"})  # first = admin
    r = client.post("/register", json={"name": "Randomer"})
    assert r.status_code == 403  # no invite -> refused


def test_invite_flow_and_role_binding(client):
    admin = client.post("/register", json={"name": "Alice"}).json()
    ah = {"Authorization": f"Bearer {admin['token']}"}

    # org_admin mints a maintainer invite via their OWN token (no admin token)
    inv = client.post("/manage/invites", headers=ah,
                      json={"role": "maintainer", "uses": 1}).json()
    assert inv["code"] and inv["role"] == "maintainer"

    # a new person redeems it -> maintainer token
    reg = client.post("/register", json={"name": "Collega", "invite_code": inv["code"]})
    assert reg.status_code == 200
    member = reg.json()
    assert member["role"] == "maintainer"
    me = client.get("/graph/me", headers={"Authorization": f"Bearer {member['token']}"}).json()
    assert me["role"] == "maintainer" and me["can_maintain"] is True and me["can_review"] is False

    # invite is single-use: second redeem fails
    assert client.post("/register", json={"name": "Derde", "invite_code": inv["code"]}).status_code == 403


def test_member_cannot_create_invite(client):
    admin = client.post("/register", json={"name": "Alice"}).json()
    ah = {"Authorization": f"Bearer {admin['token']}"}
    inv = client.post("/manage/invites", headers=ah, json={"role": "member"}).json()
    member = client.post("/register", json={"name": "Mila", "invite_code": inv["code"]}).json()
    r = client.post("/manage/invites", json={"role": "org_admin"},
                    headers={"Authorization": f"Bearer {member['token']}"})
    assert r.status_code == 403


def test_admin_api_disabled_without_admin_token(client, monkeypatch):
    from src.components.config import get_settings

    monkeypatch.setattr(get_settings(), "ADMIN_TOKEN", "")  # simulate operator not setting it
    assert client.post("/admin/orgs", json={"name": "x"},
                       headers={"Authorization": "Bearer whatever"}).status_code == 503


def test_set_token_role(client):
    admin = client.post("/register", json={"name": "Alice"}).json()
    ah = {"Authorization": f"Bearer {admin['token']}"}
    inv = client.post("/manage/invites", headers=ah, json={"role": "member"}).json()
    member = client.post("/register", json={"name": "Mila", "invite_code": inv["code"]}).json()

    accounts = client.get("/manage/accounts", headers=ah).json()
    m_acc = next(a for a in accounts if a["name"] == "Mila")
    tokens = client.get(f"/manage/accounts/{m_acc['uid']}/tokens", headers=ah).json()
    thash = tokens[0]["hash"]

    client.post(f"/manage/tokens/{thash}/role", headers=ah, json={"role": "maintainer"})
    me = client.get("/graph/me", headers={"Authorization": f"Bearer {member['token']}"}).json()
    assert me["role"] == "maintainer"


def test_org_admin_creates_account_via_manage_no_admin_token(client):
    """An org_admin creates accounts + tokens with their OWN session token via /manage —
    the operator admin token is not needed (the GUI Beheer tab relies on this)."""
    admin = client.post("/register", json={"name": "Alice"}).json()
    ah = {"Authorization": f"Bearer {admin['token']}"}

    acc = client.post("/manage/accounts", headers=ah,
                      json={"name": "Robot", "person": "Alice", "role": "member"})
    assert acc.status_code == 200
    uid = acc.json()["uid"]
    assert acc.json()["role"] == "member"

    tok = client.post("/manage/tokens", headers=ah, json={"account_uid": uid, "label": "laptop"})
    assert tok.status_code == 200 and tok.json()["token"]

    # a plain member cannot create accounts
    inv = client.post("/manage/invites", headers=ah, json={"role": "member"}).json()
    member = client.post("/register", json={"name": "Mila", "invite_code": inv["code"]}).json()
    mh = {"Authorization": f"Bearer {member['token']}"}
    assert client.post("/manage/accounts", headers=mh,
                       json={"name": "X", "role": "member"}).status_code == 403
