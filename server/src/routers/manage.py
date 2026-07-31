from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from pydantic import BaseModel

from src.authentication.deps import ROLES, AuthedAccount, require_account, require_role
from src.components.db import get_graph
from src.repository import registration_repo, tenancy_repo
from src.services import org_service
from src.models.core import (
    AccountOut,
    InviteCreate,
    OrgAccountCreate,
    TokenCreate,
    TokenOut,
    TokenRoleBody,
)

# Everything here is done with an org_admin ACCOUNT TOKEN — no operator admin token.
# All actions are scoped to the caller's own org.
router = APIRouter(prefix="/manage", tags=["manage"])


class ConsensusBody(BaseModel):
    threshold: int


@router.get("/teams")
def list_teams(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Teams in the org (name + uid) — for name-based pickers in the GUI."""
    return tenancy_repo.list_teams(session, account.org_uid)


@router.get("/swarm")
def swarm_settings(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """The Swarm's consensus threshold (min votes before a Pollen is actionable). Any member."""
    return org_service.get_swarm_settings(session, account)


@router.post("/swarm/consensus")
def set_consensus(
    body: ConsensusBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Set the minimum Swarm size for consensus (org_admin, enforced in the service)."""
    try:
        return org_service.set_consensus_threshold(session, account, body.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/invites")
def create_invite(
    body: InviteCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    try:
        return registration_repo.create_invite(
            session, account.org_uid, body.role, body.uses, body.expires_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/invites")
def list_invites(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return registration_repo.list_invites(session, account.org_uid)


@router.post("/invites/{code_hash}/revoke")
def revoke_invite(
    code_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    if not registration_repo.revoke_invite(session, account.org_uid, code_hash):
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"revoked": True}


@router.post("/accounts", response_model=AccountOut)
def create_account(
    body: OrgAccountCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Create an account in the caller's own org — the org is taken from the session token,
    so an org_admin never needs the operator admin token for this."""
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROLES)}")
    created = tenancy_repo.create_account(
        session, account.org_uid, body.name, body.team_uid, body.role, body.person, body.email
    )
    if created is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return created


@router.get("/accounts")
def list_accounts(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return tenancy_repo.list_accounts(session, account.org_uid)


@router.get("/accounts/{account_uid}/tokens")
def list_tokens(
    account_uid: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return tenancy_repo.list_tokens(session, account_uid)


@router.post("/tokens", response_model=TokenOut)
def create_token(
    body: TokenCreate,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    token = tenancy_repo.create_token(session, body.account_uid, body.label,
                                      body.expires_days, body.role)
    if token is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return token


@router.post("/tokens/{token_hash}/role")
def set_token_role(
    token_hash: str,
    body: TokenRoleBody,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """Bind a role to a specific token (member/maintainer/org_admin)."""
    if body.role not in registration_repo.VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {registration_repo.VALID_ROLES}")
    if not tenancy_repo.set_token_role(session, token_hash, body.role):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"role": body.role}


@router.post("/tokens/{token_hash}/rotate", response_model=TokenOut)
def rotate_token(
    token_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    fresh = tenancy_repo.rotate_token(session, token_hash, None)
    if fresh is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return fresh


@router.post("/tokens/{token_hash}/revoke")
def revoke_token(
    token_hash: str,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    if not tenancy_repo.revoke_token(session, token_hash):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"revoked": True}


@router.post("/tokens/cleanup")
def cleanup_tokens(
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    return {"removed": tenancy_repo.cleanup_tokens(session, account.org_uid)}
