from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from neo4j import Session

from src.components.config import get_settings
from src.components.db import get_graph


ROLES = ("member", "maintainer", "org_admin")
_ROLE_ORDER = {role: i for i, role in enumerate(ROLES)}


@dataclass
class AuthedAccount:
    uid: str
    org_uid: str
    team_uid: str | None
    name: str
    role: str


def has_role(account: AuthedAccount, minimum: str) -> bool:
    return _ROLE_ORDER.get(account.role, 0) >= _ROLE_ORDER[minimum]


def effective_role(account_role: str | None, token_role: str | None) -> str:
    """Which role a request actually runs with.

    A token carries its own role so you can hand out a narrowed one — a read-only
    token for a script, say — and that is why the token normally wins. The one
    exception is org_admin: that role means "may do everything in this org", so an
    org_admin's request is never narrowed by whichever token it arrived on. Without
    that floor the member list in the GUI (which shows the ACCOUNT role) and the
    API (which enforced only the TOKEN role) could disagree, and an org_admin would
    be told "requires the 'maintainer' role (your role: 'member')" about their own
    hive.
    """
    if account_role == "org_admin":
        return "org_admin"
    return token_role or account_role or "member"


def assert_role(account: AuthedAccount, minimum: str, action: str) -> None:
    if not has_role(account, minimum):
        raise ValueError(
            f"{action} requires the '{minimum}' role (your role: '{account.role}'). "
            "Ask an admin to grant it to your account."
        )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def account_from_token(session: Session, token: str) -> AuthedAccount:
    record = session.run(
        """
        MATCH (a:Account)-[:HAS_TOKEN]->(t:Token {hash: $hash})
        WHERE t.revoked = false AND (t.expires_at IS NULL OR t.expires_at > timestamp())
        SET t.last_used = timestamp()
        RETURN a.uid AS uid, a.org_uid AS org_uid, a.team_uid AS team_uid,
               a.name AS name, coalesce(t.role, a.role, 'member') AS token_role,
               a.role AS account_role
        """,
        hash=hash_token(token),
    ).single()
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return AuthedAccount(
        uid=record["uid"],
        org_uid=record["org_uid"],
        team_uid=record["team_uid"],
        name=record["name"],
        role=effective_role(record["account_role"], record["token_role"]),
    )


def _bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    return authorization.removeprefix("Bearer ").strip()


def require_account(
    authorization: str = Header(...), session: Session = Depends(get_graph)
) -> AuthedAccount:
    return account_from_token(session, _bearer(authorization))


def require_role(minimum: str):
    """FastAPI dependency factory: gate an endpoint on a token role (not the admin token)."""
    def _dep(account: AuthedAccount = Depends(require_account)) -> AuthedAccount:
        if not has_role(account, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{minimum}' role required (your role: '{account.role}')",
            )
        return account
    return _dep


def require_admin(authorization: str = Header(...)) -> None:
    """Operator break-glass via ADMIN_TOKEN. Optional: when ADMIN_TOKEN is unset the
    /admin API is disabled and everything runs through org_admin tokens + registration."""
    admin_token = get_settings().ADMIN_TOKEN
    if not admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API disabled (no ADMIN_TOKEN). Use an org_admin account token via /manage.",
        )
    if _bearer(authorization) != admin_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
