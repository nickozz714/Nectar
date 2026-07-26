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
