from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.authentication.deps import AuthedAccount, has_role, require_account
from src.components.db import get_graph
from src.repository import governance_repo
from src.models.core import ChoreDecision, ChoreOut
from src.services import governance_service

router = APIRouter(prefix="/review", tags=["review"])


def _require_org_admin(account: AuthedAccount) -> None:
    if not has_role(account, "org_admin"):
        raise HTTPException(status_code=403, detail="org_admin role required")


@router.get("/chores", response_model=list[ChoreOut])
def review_queue(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """The human review queue for this org — scope-widening decisions. Reviewers use
    their own account token (org_admin role), not the infra admin token."""
    _require_org_admin(account)
    return governance_repo.chores_by_status(session, account.org_uid, "awaiting_human")


@router.post("/chores/{chore_uid}/approve")
def approve(
    chore_uid: str,
    body: ChoreDecision,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    _require_org_admin(account)
    try:
        return governance_service.approve_scope_widening(
            session, chore_uid, account.org_uid, body.note, reviewed_by=account.name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chores/{chore_uid}/reject")
def reject(
    chore_uid: str,
    body: ChoreDecision,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    _require_org_admin(account)
    chore = governance_repo.get_chore(session, account.org_uid, chore_uid)
    if chore is None or chore["status"] != "awaiting_human":
        raise HTTPException(status_code=404, detail="Chore not found or not awaiting review")
    governance_repo.close_chore(session, chore_uid, "rejected", account.name, body.note)
    return {"status": "rejected"}
