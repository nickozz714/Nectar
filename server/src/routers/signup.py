from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.config import get_settings
from src.db.neo4j import get_graph
from src.schemas.core import RegisterBody
from src.repository import registration_repo

router = APIRouter(tags=["registration"])


@router.get("/register")
def register_status(session: Session = Depends(get_graph)):
    """Whether the hive still needs its first user (then registration is open once) or is
    invite-only. Lets a client decide what to ask for."""
    first = registration_repo.org_count(session) == 0
    return {"first_run": first,
            "needs_invite": not first,
            "note": "First registration creates the org and becomes org_admin; "
                    "after that an invite code is required."}


@router.post("/register")
def register(body: RegisterBody, session: Session = Depends(get_graph)):
    """Self-service registration. The FIRST user bootstraps the org as org_admin with no
    token needed; every later user must present an invite code. Returns an account token —
    the only thing a client needs from then on. The role is bound to that token."""
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="name required")

    if registration_repo.org_count(session) == 0:
        return registration_repo.register_first(
            session, get_settings().HIVE_ORG_NAME, name, body.email
        )

    if not body.invite_code:
        raise HTTPException(
            status_code=403,
            detail="Registration is invite-only. Ask an org_admin for an invite code.",
        )
    result = registration_repo.redeem_invite(session, body.invite_code.strip(), name, body.email)
    if result is None:
        raise HTTPException(status_code=403, detail="Invalid, expired or exhausted invite code")
    return result
