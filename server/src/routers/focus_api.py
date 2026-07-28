from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session
from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import get_graph
from src.repository import focus_repo

# Read/steer the active focus from the GUI. Everything is scoped to the caller's own account
# (the token), across all their projects.
router = APIRouter(prefix="/focus", tags=["focus"])


class FocusBody(BaseModel):
    goal: str
    steps: list = []          # list of strings or {text,status}
    guardrails: list[str] = []
    done_when: str = ""
    project: str = ""


class AdvanceBody(BaseModel):
    completed_step: str | int | None = None
    note: str | None = None
    project: str = ""


@router.get("")
def list_focus(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """All active foci for this account, across projects."""
    return focus_repo.list_for(session, account)


@router.post("")
def set_focus(
    body: FocusBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return focus_repo.set_focus(session, account, body.goal, body.steps,
                                body.guardrails, body.done_when, project=body.project)


@router.post("/advance")
def advance_focus(
    body: AdvanceBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return focus_repo.advance_focus(session, account, body.completed_step,
                                    body.note, project=body.project) or {"active": False}


@router.delete("")
def clear_focus(
    project: str = "",
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {"cleared": focus_repo.clear_focus(session, account, project=project)}
