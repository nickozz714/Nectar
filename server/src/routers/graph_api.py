from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from collections import Counter

from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, has_role, require_account
from src.db.neo4j import get_graph
from src.repository import audit_repo, governance_repo, graph_repo
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
        "person": graph_repo.account_info(session, account.uid).get("person"),
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


@router.get("/lineage/{uid}")
def lineage(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Purview-style lineage for one knowledge node: who (person) via which account and
    model created it, and every governance event that touched it since."""
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    creator = graph_repo.account_info(session, node.get("created_by"))
    return {
        "uid": uid,
        "title": node.get("title"),
        "created_at": node.get("created"),
        "created_by_account": creator.get("name"),
        "created_by_person": creator.get("person"),
        "created_by_model": node.get("created_by_model") or "onbekend",
        "sensitivity": node.get("sensitivity", "intern"),
        "scope": node.get("scope"),
        "use_count": node.get("use_count", 0),
        "events": audit_repo.events_for_target(session, account.org_uid, uid),
    }


@router.get("/governance")
def governance(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Purview-style transparency: what lives in the mind, how it is classified, who/what
    wrote it, and where governance work stands. Visible to every member — the hive must
    be open about itself."""
    rows = graph_repo.governance_rows(session, account)
    return {
        "nodes_total": len(rows),
        "by_scope": dict(Counter(r["scope"] for r in rows)),
        "by_type": dict(Counter(r["type"] for r in rows)),
        "by_sensitivity": dict(Counter(r["sensitivity"] for r in rows)),
        "by_model": dict(Counter(r["model"] or "onbekend" for r in rows)),
        "sensitive_nodes": [
            {"uid": r["uid"], "title": r["title"], "type": r["type"]}
            for r in rows if r["sensitivity"] == "gevoelig"
        ],
        "chores": graph_repo.chore_status_counts(session, account.org_uid),
    }


@router.get("/audit")
def audit(
    limit: int = 100,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Append-only audit trail (org_admin): every write, mutation and secret access."""
    if not has_role(account, "org_admin"):
        raise HTTPException(status_code=403, detail="org_admin role required")
    return audit_repo.recent(session, account.org_uid, min(limit, 500))


class SuggestBody(BaseModel):
    kind: str
    node_uid: str
    payload: dict = {}
    rationale: str = ""
    model_name: str = ""


@router.post("/suggest")
def suggest(
    body: SuggestBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """File a mutation suggestion from the GUI (same consensus path as the MCP tool)."""
    try:
        return governance_service.suggest(
            session, account, body.kind, body.node_uid, body.payload,
            body.rationale, body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
