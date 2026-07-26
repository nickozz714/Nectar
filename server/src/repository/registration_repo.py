from __future__ import annotations

import secrets as pysecrets

from neo4j import Session

from src.authentication.deps import hash_token
from src.repository import tenancy_repo

VALID_ROLES = ("member", "maintainer", "org_admin")


def org_count(session: Session) -> int:
    return session.run("MATCH (o:Org) RETURN count(o) AS n").single()["n"]


def register_first(session: Session, org_name: str, name: str, email: str | None) -> dict:
    """Bootstrap: the very first self-registration creates the org and becomes org_admin.
    No admin token needed for day one; afterwards registration is invite-only."""
    org = tenancy_repo.create_org(session, org_name)
    account = tenancy_repo.create_account(
        session, org["uid"], name, None, "org_admin", person=name, email=email
    )
    token = tenancy_repo.create_token(session, account["uid"], "self-register", None, role="org_admin")
    return {"token": token["token"], "role": "org_admin", "org_uid": org["uid"],
            "note": "first user — created the org and got org_admin"}


def create_invite(
    session: Session, org_uid: str, role: str, uses: int, expires_days: int | None
) -> dict:
    """Mint an invite code (hashed at rest, returned once). Redeemers get its role."""
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    code = pysecrets.token_urlsafe(9)
    session.run(
        """
        MATCH (o:Org {uid: $org_uid})
        CREATE (i:Invite {code_hash: $hash, org_uid: $org_uid, role: $role,
                          uses_left: $uses, created: timestamp(),
                          expires_at: CASE WHEN $expires_days IS NULL THEN NULL
                                      ELSE timestamp() + $expires_days * 86400000 END})
        """,
        org_uid=org_uid,
        hash=hash_token(code),
        role=role,
        uses=uses,
        expires_days=expires_days,
    )
    return {"code": code, "role": role, "uses": uses}


def redeem_invite(session: Session, code: str, name: str, email: str | None) -> dict | None:
    """Validate an invite and create an account + token with the invite's role."""
    invite = session.run(
        """
        MATCH (i:Invite {code_hash: $hash})
        WHERE i.uses_left > 0 AND (i.expires_at IS NULL OR i.expires_at > timestamp())
        SET i.uses_left = i.uses_left - 1
        RETURN i.org_uid AS org_uid, i.role AS role
        """,
        hash=hash_token(code),
    ).single()
    if invite is None:
        return None
    account = tenancy_repo.create_account(
        session, invite["org_uid"], name, None, invite["role"], person=name, email=email
    )
    if account is None:
        return None
    token = tenancy_repo.create_token(
        session, account["uid"], "self-register", None, role=invite["role"]
    )
    return {"token": token["token"], "role": invite["role"], "org_uid": invite["org_uid"]}


def list_invites(session: Session, org_uid: str) -> list[dict]:
    result = session.run(
        """
        MATCH (i:Invite {org_uid: $org_uid})
        RETURN i.code_hash AS code_hash, i.role AS role, i.uses_left AS uses_left,
               i.created AS created, i.expires_at AS expires_at
        ORDER BY i.created DESC
        """,
        org_uid=org_uid,
    )
    return [dict(r) for r in result]


def revoke_invite(session: Session, org_uid: str, code_hash: str) -> bool:
    record = session.run(
        "MATCH (i:Invite {org_uid: $org_uid, code_hash: $hash}) SET i.uses_left = 0 "
        "RETURN i.code_hash AS h",
        org_uid=org_uid,
        hash=code_hash,
    ).single()
    return record is not None
