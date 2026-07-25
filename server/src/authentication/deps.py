from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from neo4j import Session

from src.config import get_settings
from src.db.neo4j import get_graph


@dataclass
class AuthedAccount:
    uid: str
    org_uid: str
    team_uid: str | None
    name: str
    role: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def account_from_token(session: Session, token: str) -> AuthedAccount:
    record = session.run(
        """
        MATCH (a:Account)-[:HAS_TOKEN]->(t:Token {hash: $hash})
        WHERE t.revoked = false AND (t.expires_at IS NULL OR t.expires_at > timestamp())
        SET t.last_used = timestamp()
        RETURN a.uid AS uid, a.org_uid AS org_uid, a.team_uid AS team_uid,
               a.name AS name, a.role AS role
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
        role=record["role"] or "member",
    )


def _bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    return authorization.removeprefix("Bearer ").strip()


def require_account(
    authorization: str = Header(...), session: Session = Depends(get_graph)
) -> AuthedAccount:
    return account_from_token(session, _bearer(authorization))


def require_admin(authorization: str = Header(...)) -> None:
    if _bearer(authorization) != get_settings().ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
