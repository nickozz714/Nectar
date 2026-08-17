from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session
from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, require_account
from src.components.db import get_graph
from src.repository import focus_repo

# Read/steer the active foci from the GUI. Everything is scoped to the caller's own account
# (the token), across all their projects. A project can hold SEVERAL foci — one per lane — so
# parallel sessions each steer their own task; `lane` addresses one of them ("" = project-wide).
router = APIRouter(prefix="/focus", tags=["focus"])


class FocusBody(BaseModel):
    goal: str
    steps: list = []          # list of strings or {text,status}
    guardrails: list[str] = []
    done_when: str = ""
    project: str = ""
    lane: str | None = None   # exact lane key (from GET /focus); None -> derive from session/name
    name: str = ""            # human lane name — creates/joins a named lane
    session: str = ""         # client session id — binds this session to the lane


class AdvanceBody(BaseModel):
    completed_step: str | int | None = None
    note: str | None = None
    project: str = ""
    lane: str | None = None
    name: str = ""
    session: str = ""


class BindBody(BaseModel):
    project: str = ""
    lane: str = ""
    session: str = ""


@router.get("")
def list_focus(
    project: str | None = None,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """All active foci (lanes) for this account — across projects, or within one project."""
    return focus_repo.list_for(session, account, project=project)


@router.post("")
def set_focus(
    body: FocusBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return focus_repo.set_focus(session, account, body.goal, body.steps,
                                body.guardrails, body.done_when, project=body.project,
                                session_id=body.session, name=body.name, lane=body.lane)


@router.post("/advance")
def advance_focus(
    body: AdvanceBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return focus_repo.advance_focus(session, account, body.completed_step, body.note,
                                    project=body.project, session_id=body.session,
                                    name=body.name, lane=body.lane) or {"active": False}


@router.post("/bind")
def bind_focus(
    body: BindBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Attach a session to an existing lane, so that session's recall resolves to this focus."""
    return {"bound": focus_repo.bind_session(session, account, body.project,
                                             body.lane, body.session)}


@router.delete("")
def clear_focus(
    project: str = "",
    lane: str | None = None,
    name: str = "",
    session_id: str = "",
    all_lanes: bool = False,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    removed = focus_repo.clear_focus(session, account, project=project, lane=lane,
                                     name=name, session_id=session_id, all_lanes=all_lanes)
    return {"cleared": removed > 0, "removed": removed}
