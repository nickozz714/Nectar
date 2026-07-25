from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.authentication.deps import AuthedAccount, has_role, require_account
from src.db.neo4j import get_graph
from src.repository import governance_repo, graph_repo
from src.schemas.core import ChoreDecision
from src.services import governance_service, search_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/me")
def me(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "name": account.name,
        "role": account.role,
        "org_uid": account.org_uid,
        "team_uid": account.team_uid,
        "can_maintain": has_role(account, "maintainer"),
        "can_review": has_role(account, "org_admin"),
        "ready_chores": governance_repo.ready_count(session, account),
    }


@router.get("/topics")
def topics(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "topics": graph_repo.list_topics(session, account),
        "edges": graph_repo.topic_edges(session, account),
    }


@router.get("/search")
def search(
    q: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    # Browsing in the GUI should not rejuvenate memories — only actual use does.
    results = search_service.search(session, account, q, limit=12, touch=False)
    return [
        {"uid": n["uid"], "title": n["title"], "type": n["type"],
         "scope": n.get("scope"), "topics": n.get("topics", [])}
        for n in results
    ]


@router.get("/node/{uid}")
def node(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    data = graph_repo.get_node(session, account, uid)
    if data is None:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    files = graph_repo.node_files(session, account, uid)
    if files:
        data["files"] = files
    return data


@router.get("/neighbors/{uid}")
def node_neighbors(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    data = graph_repo.neighbors(session, account, uid)
    if not data:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    return data


@router.get("/chores")
def chores(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "ready": governance_repo.ready_count(session, account),
        "chores": governance_repo.open_chores(session, account, limit=25),
    }


@router.post("/chores/{chore_uid}/resolve")
def resolve_chore(
    chore_uid: str,
    body: ChoreDecision,
    action: str = "apply",
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return governance_service.resolve(session, account, chore_uid, action, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
