"""Org administration from an org_admin token: invites, member list, role changes."""
from __future__ import annotations

import pytest

from src.services import org_service


def test_org_admin_creates_invite_member_cannot(graph, account):
    admin = account("nick", role="org_admin")
    member = account("collega", role="member")

    inv = org_service.create_invite(graph, admin, "maintainer", 1, 14)
    assert inv["code"] and inv["role"] == "maintainer"

    with pytest.raises(ValueError, match="org_admin"):
        org_service.create_invite(graph, member, "member", 1, 14)


def test_list_members(graph, account):
    admin = account("nick", role="org_admin")
    account("collega", role="member")
    members = org_service.list_members(graph, admin)
    names = {m["name"]: m["role"] for m in members}
    assert names.get("nick") == "org_admin" and names.get("collega") == "member"


def test_promote_and_demote(graph, account, org):
    from src.authentication.deps import account_from_token
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    # a member with an actual token so we can check the effective (token-bound) role
    m = tenancy_repo.create_account(graph, org["org_uid"], "collega", None, "member", person="C")
    tok = tenancy_repo.create_token(graph, m["uid"], "laptop", None, role="member")["token"]

    org_service.set_role(graph, admin, "collega", "maintainer")
    assert account_from_token(graph, tok).role == "maintainer"

    org_service.set_role(graph, admin, "collega", "member")
    assert account_from_token(graph, tok).role == "member"


def test_set_role_unknown_account(graph, account):
    admin = account("nick", role="org_admin")
    with pytest.raises(ValueError, match="No account"):
        org_service.set_role(graph, admin, "bestaat-niet", "maintainer")


# ─── Role changes from the GUI (by account uid / per token) ──────────────────────────

def test_set_role_by_uid_applies_to_account_and_tokens(graph, account, org):
    from src.authentication.deps import account_from_token
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    m = tenancy_repo.create_account(graph, org["org_uid"], "collega", None, "member", person="C")
    tok = tenancy_repo.create_token(graph, m["uid"], "laptop", None, role="member")["token"]

    out = org_service.set_role_by_uid(graph, admin, m["uid"], "maintainer")
    assert out["account"] == "collega" and out["role"] == "maintainer" and out["previous"] == "member"
    assert account_from_token(graph, tok).role == "maintainer"


def test_set_role_by_uid_rejects_unknown_and_bad_role(graph, account, org):
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    m = tenancy_repo.create_account(graph, org["org_uid"], "collega", None, "member")
    with pytest.raises(ValueError, match="No such account"):
        org_service.set_role_by_uid(graph, admin, "bestaat-niet", "member")
    with pytest.raises(ValueError, match="role must be one of"):
        org_service.set_role_by_uid(graph, admin, m["uid"], "koning")


def test_member_cannot_change_roles(graph, account, org):
    from src.repository import tenancy_repo

    account("nick", role="org_admin")
    member = account("collega", role="member")
    target = tenancy_repo.create_account(graph, org["org_uid"], "derde", None, "member")
    with pytest.raises(ValueError, match="org_admin"):
        org_service.set_role_by_uid(graph, member, target["uid"], "org_admin")


def test_last_org_admin_cannot_be_demoted(graph, account, org):
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    me = tenancy_repo.list_accounts(graph, org["org_uid"])
    mine = next(a for a in me if a["name"] == "nick")
    with pytest.raises(ValueError, match="last org_admin"):
        org_service.set_role_by_uid(graph, admin, mine["uid"], "member")
    with pytest.raises(ValueError, match="last org_admin"):
        org_service.set_role(graph, admin, "nick", "member")

    # with a second org_admin around, demoting the first is fine
    second = tenancy_repo.create_account(graph, org["org_uid"], "tweede", None, "org_admin")
    assert org_service.set_role_by_uid(graph, admin, mine["uid"], "member")["role"] == "member"
    assert org_service.set_role_by_uid(graph, account("tweede-admin", role="org_admin"),
                                      second["uid"], "maintainer")["role"] == "maintainer"


def test_token_role_is_scoped_to_own_org(graph, account, org):
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    other_org = tenancy_repo.create_org(graph, "AndereOrg")
    outsider = tenancy_repo.create_account(graph, other_org["uid"], "vreemde", None, "member")
    foreign = tenancy_repo.create_token(graph, outsider["uid"], "t", None, role="member")
    foreign_hash = tenancy_repo.hash_token(foreign["token"])
    with pytest.raises(ValueError, match="No such token"):
        org_service.set_token_role(graph, admin, foreign_hash, "org_admin")


def test_token_role_change_leaves_account_role_alone(graph, account, org):
    from src.authentication.deps import account_from_token
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    m = tenancy_repo.create_account(graph, org["org_uid"], "collega", None, "maintainer")
    t = tenancy_repo.create_token(graph, m["uid"], "ci-runner", None, role="maintainer")

    org_service.set_token_role(graph, admin, tenancy_repo.hash_token(t["token"]), "member")
    assert account_from_token(graph, t["token"]).role == "member"          # this token
    assert tenancy_repo.get_account(graph, org["org_uid"], m["uid"])["role"] == "maintainer"


def test_role_endpoints_over_http(client, graph, account, org):
    from src.repository import tenancy_repo

    admin = account("nick", role="org_admin")
    admin_tok = tenancy_repo.create_token(graph, admin.uid, "gui", None, role="org_admin")["token"]
    h = {"Authorization": f"Bearer {admin_tok}"}
    m = tenancy_repo.create_account(graph, org["org_uid"], "collega", None, "member")
    t = tenancy_repo.create_token(graph, m["uid"], "laptop", None, role="member")
    t_hash = tenancy_repo.hash_token(t["token"])

    r = client.post(f"/manage/accounts/{m['uid']}/role", headers=h, json={"role": "maintainer"})
    assert r.status_code == 200 and r.json()["role"] == "maintainer"
    listed = {a["name"]: a["role"] for a in client.get("/manage/accounts", headers=h).json()}
    assert listed["collega"] == "maintainer"

    r = client.post(f"/manage/tokens/{t_hash}/role", headers=h, json={"role": "member"})
    assert r.status_code == 200 and r.json()["role"] == "member"

    # bad role and unknown account are 400/404, not a 500
    assert client.post(f"/manage/accounts/{m['uid']}/role", headers=h,
                       json={"role": "koning"}).status_code == 400
    assert client.post("/manage/accounts/onbekend/role", headers=h,
                       json={"role": "member"}).status_code == 400
    assert client.post("/manage/tokens/geen-token/role", headers=h,
                       json={"role": "member"}).status_code == 404

    # and a plain member is refused
    member_tok = tenancy_repo.create_token(graph, m["uid"], "eigen", None, role="member")["token"]
    assert client.post(f"/manage/accounts/{m['uid']}/role",
                       headers={"Authorization": f"Bearer {member_tok}"},
                       json={"role": "org_admin"}).status_code == 403
