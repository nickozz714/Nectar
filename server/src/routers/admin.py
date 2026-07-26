from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.authentication.deps import ROLES, require_admin
from src.db.neo4j import get_graph
from src.repository import governance_repo, tenancy_repo, vault_repo
from src.schemas.core import (
    AccountCreate,
    AccountOut,
    ChoreDecision,
    ChoreOut,
    OrgCreate,
    OrgOut,
    SecretGrantCreate,
    TeamCreate,
    TeamOut,
    TokenCreate,
    TokenOut,
)
from src.services import governance_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/orgs", response_model=OrgOut)
def create_org(body: OrgCreate, session: Session = Depends(get_graph)):
    return tenancy_repo.create_org(session, body.name)


@router.post("/teams", response_model=TeamOut)
def create_team(body: TeamCreate, session: Session = Depends(get_graph)):
    team = tenancy_repo.create_team(session, body.org_uid, body.name)
    if team is None:
        raise HTTPException(status_code=404, detail="Org not found")
    return team


@router.post("/accounts", response_model=AccountOut)
def create_account(body: AccountCreate, session: Session = Depends(get_graph)):
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROLES)}")
    account = tenancy_repo.create_account(
        session, body.org_uid, body.name, body.team_uid, body.role, body.person
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Org or team not found")
    return account


@router.post("/tokens", response_model=TokenOut)
def create_token(body: TokenCreate, session: Session = Depends(get_graph)):
    token = tenancy_repo.create_token(session, body.account_uid, body.label, body.expires_days)
    if token is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return token


@router.post("/tokens/{token_hash}/revoke")
def revoke_token(token_hash: str, session: Session = Depends(get_graph)):
    if not tenancy_repo.revoke_token(session, token_hash):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


@router.post("/secret-grants")
def grant_secret(body: SecretGrantCreate, session: Session = Depends(get_graph)):
    if not vault_repo.grant_secret(session, body.org_uid, body.name, body.account_uid):
        raise HTTPException(status_code=404, detail="Secret or account not found")
    return {"granted": True}


@router.get("/secrets")
def list_secrets(org_uid: str, session: Session = Depends(get_graph)):
    return vault_repo.list_secret_names(session, org_uid)


@router.get("/chores", response_model=list[ChoreOut])
def review_queue(
    status: str = "awaiting_human", org_uid: str | None = None,
    session: Session = Depends(get_graph),
):
    """The human review queue — scope-widening decisions land here."""
    return governance_repo.chores_by_status(session, org_uid, status)


@router.post("/chores/{chore_uid}/approve")
def approve_chore(
    chore_uid: str, org_uid: str, body: ChoreDecision, session: Session = Depends(get_graph)
):
    try:
        return governance_service.approve_scope_widening(session, chore_uid, org_uid, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chores/{chore_uid}/reject")
def reject_chore(
    chore_uid: str, org_uid: str, body: ChoreDecision, session: Session = Depends(get_graph)
):
    chore = governance_repo.get_chore(session, org_uid, chore_uid)
    if chore is None:
        raise HTTPException(status_code=404, detail="Chore not found")
    governance_repo.close_chore(session, chore_uid, "rejected", "human-admin", body.note)
    return {"status": "rejected"}
