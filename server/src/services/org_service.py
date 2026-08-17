from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.components.config import get_settings
from src.repository import audit_repo, registration_repo, tenancy_repo

VALID_ROLES = registration_repo.VALID_ROLES


def create_invite(
    session: Session, account: AuthedAccount, role: str, uses: int, expires_days: int | None
) -> dict:
    assert_role(account, "org_admin", "Creating invites")
    result = registration_repo.create_invite(session, account.org_uid, role, uses, expires_days)
    audit_repo.log(session, account.org_uid, account.uid, "invite_create", result["code"][:4] + "…",
                   {"role": role, "uses": uses})
    return result


def list_members(session: Session, account: AuthedAccount) -> list[dict]:
    assert_role(account, "org_admin", "Listing members")
    return [{"uid": a["uid"], "name": a["name"], "person": a["person"], "role": a["role"],
             "active_tokens": a["active"]}
            for a in tenancy_repo.list_accounts(session, account.org_uid)]


def _assert_not_last_org_admin(session: Session, org_uid: str, current_role: str, new_role: str) -> None:
    """Refuse a demotion that would leave the org without a single org_admin — nobody could
    then manage members, roles or tokens any more (only the operator admin token could)."""
    if current_role == "org_admin" and new_role != "org_admin" \
            and tenancy_repo.count_accounts_with_role(session, org_uid, "org_admin") <= 1:
        raise ValueError("This is the last org_admin — promote someone else first, "
                         "otherwise nobody can manage the org any more")


def set_role(session: Session, account: AuthedAccount, target_name: str, role: str) -> dict:
    assert_role(account, "org_admin", "Changing roles")
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    members = {a["name"]: a for a in tenancy_repo.list_accounts(session, account.org_uid)}
    target = members.get(target_name)
    if target is None:
        raise ValueError(f"No account named '{target_name}' in your org")
    _assert_not_last_org_admin(session, account.org_uid, target["role"], role)
    if not tenancy_repo.set_account_role(session, account.org_uid, target_name, role):
        raise ValueError(f"No account named '{target_name}' in your org")
    audit_repo.log(session, account.org_uid, account.uid, "set_role", target_name, {"role": role})
    return {"account": target_name, "role": role,
            "note": "role applied to the account and all its tokens"}


def set_role_by_uid(session: Session, account: AuthedAccount, account_uid: str, role: str) -> dict:
    """Promote/demote by account uid — what the GUI's member list works with. Applies the role
    to the account AND all its tokens (the role is token-bound, so both must move)."""
    assert_role(account, "org_admin", "Changing roles")
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    target = tenancy_repo.get_account(session, account.org_uid, account_uid)
    if target is None:
        raise ValueError("No such account in your org")
    _assert_not_last_org_admin(session, account.org_uid, target["role"], role)
    updated = tenancy_repo.set_account_role_by_uid(session, account.org_uid, account_uid, role)
    audit_repo.log(session, account.org_uid, account.uid, "set_role", updated["name"],
                   {"role": role, "previous": updated["previous"]})
    return {"uid": updated["uid"], "account": updated["name"], "role": role,
            "previous": updated["previous"],
            "note": "role applied to the account and all its tokens"}


def set_token_role(session: Session, account: AuthedAccount, token_hash: str, role: str) -> dict:
    """Bind a role to ONE token (a machine may be allowed less than its owner account). Scoped
    to the caller's own org, and audited. The account's own role is left untouched."""
    assert_role(account, "org_admin", "Changing roles")
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    owner = tenancy_repo.token_owner(session, token_hash)
    if owner is None or owner["org_uid"] != account.org_uid:
        raise ValueError("No such token in your org")
    if not tenancy_repo.set_token_role(session, token_hash, role):
        raise ValueError("No such token in your org")
    audit_repo.log(session, account.org_uid, account.uid, "set_token_role",
                   owner["account_name"], {"role": role, "token": token_hash[:8] + "…"})
    return {"account": owner["account_name"], "role": role, "token_hash": token_hash}


def get_swarm_settings(session: Session, account: AuthedAccount) -> dict:
    """Swarm governance settings visible to any member: the consensus threshold = the minimum
    number of distinct votes before a Pollen becomes actionable ('ready'), plus whether
    cognition-Pollen (optional world research on new memories) is on."""
    s = get_settings()
    threshold = tenancy_repo.get_consensus_threshold(session, account.org_uid, s.CONSENSUS_THRESHOLD)
    return {
        "consensus_threshold": threshold,
        "default": s.CONSENSUS_THRESHOLD,
        "cognition_enabled": tenancy_repo.get_cognition_enabled(session, account.org_uid),
        "cognition_budget": {"max_new": s.COGNITION_MAX_NEW_MEMORIES,
                             "max_depth": s.COGNITION_MAX_DEPTH,
                             "daily_cap": s.COGNITION_DAILY_CAP},
    }


def set_consensus_threshold(session: Session, account: AuthedAccount, n: int) -> dict:
    """Set the minimum Swarm size for consensus. 1 = a single vote makes a Pollen ready
    (right for a solo/small swarm). org_admin only."""
    assert_role(account, "org_admin", "Changing the Swarm consensus threshold")
    if not isinstance(n, int) or n < 1:
        raise ValueError("consensus_threshold must be an integer >= 1")
    tenancy_repo.set_consensus_threshold(session, account.org_uid, n)
    audit_repo.log(session, account.org_uid, account.uid, "set_consensus_threshold",
                   account.org_uid, {"threshold": n})
    return {"consensus_threshold": n}


def set_default_ui(session: Session, account: AuthedAccount, ui: str) -> dict:
    """Choose the org's default interface after login: 'legacy' or 'mind' (3D HUD).
    Both stay available; this only decides where members land. org_admin only."""
    assert_role(account, "org_admin", "Changing the default interface")
    if ui not in ("legacy", "mind"):
        raise ValueError("ui must be 'legacy' or 'mind'")
    tenancy_repo.set_default_ui(session, account.org_uid, ui)
    audit_repo.log(session, account.org_uid, account.uid, "set_default_ui",
                   account.org_uid, {"ui": ui})
    return {"default_ui": ui}


def set_cognition_enabled(session: Session, account: AuthedAccount, on: bool) -> dict:
    """Toggle cognition-Pollen: optional world research on newly written memories
    (docs/COGNITION.md). Off by default — it costs web searches and tokens. org_admin only."""
    assert_role(account, "org_admin", "Toggling cognition")
    tenancy_repo.set_cognition_enabled(session, account.org_uid, bool(on))
    audit_repo.log(session, account.org_uid, account.uid, "set_cognition_enabled",
                   account.org_uid, {"enabled": bool(on)})
    return {"cognition_enabled": bool(on)}
