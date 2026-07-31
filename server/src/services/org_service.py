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
    return [{"name": a["name"], "person": a["person"], "role": a["role"],
             "active_tokens": a["active"]}
            for a in tenancy_repo.list_accounts(session, account.org_uid)]


def set_role(session: Session, account: AuthedAccount, target_name: str, role: str) -> dict:
    assert_role(account, "org_admin", "Changing roles")
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    if not tenancy_repo.set_account_role(session, account.org_uid, target_name, role):
        raise ValueError(f"No account named '{target_name}' in your org")
    audit_repo.log(session, account.org_uid, account.uid, "set_role", target_name, {"role": role})
    return {"account": target_name, "role": role,
            "note": "role applied to the account and all its tokens"}


def get_swarm_settings(session: Session, account: AuthedAccount) -> dict:
    """Swarm governance settings visible to any member: the consensus threshold = the minimum
    number of distinct votes before a Pollen becomes actionable ('ready')."""
    threshold = tenancy_repo.get_consensus_threshold(
        session, account.org_uid, get_settings().CONSENSUS_THRESHOLD)
    return {"consensus_threshold": threshold, "default": get_settings().CONSENSUS_THRESHOLD}


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
