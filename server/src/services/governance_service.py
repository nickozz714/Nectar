from __future__ import annotations

import json

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.config import get_settings
from src.repository import audit_repo, governance_repo, graph_repo
from src.services.embeddings import embed


def suggest(
    session: Session,
    account: AuthedAccount,
    chore_type: str,
    node_uid: str,
    payload: dict,
    rationale: str,
    model_name: str,
) -> dict:
    if chore_type not in governance_repo.CHORE_TYPES:
        raise ValueError(f"kind must be one of: {', '.join(sorted(governance_repo.CHORE_TYPES))}")
    result = governance_repo.suggest(
        session, account, chore_type, node_uid, payload, rationale, model_name,
        threshold=get_settings().CONSENSUS_THRESHOLD,
    )
    if result is None:
        raise ValueError("Node not found or not visible to this account")
    audit_repo.log(session, account.org_uid, account.uid, "suggest", node_uid,
                   {"kind": chore_type, "chore": result["uid"]})
    return result


def resolve(
    session: Session, account: AuthedAccount, chore_uid: str, action: str, note: str
) -> dict:
    """A bee resolves a 'ready' chore. scope_widening never passes through here —
    that is the one mutation reserved for a human (admin API)."""
    chore = governance_repo.get_chore(session, account.org_uid, chore_uid)
    if chore is None:
        raise ValueError("Chore not found")
    if chore["status"] != "ready":
        raise ValueError(f"Chore is '{chore['status']}', only 'ready' chores can be resolved by the swarm")
    if chore["type"] == "scope_widening":
        raise ValueError("scope_widening is decided by a human via the admin review queue")
    if action == "reject":
        governance_repo.close_chore(session, chore_uid, "rejected", account.uid, note)
        return {"status": "rejected"}
    if action != "apply":
        raise ValueError("action must be apply or reject")

    payload = json.loads(chore["payload"] or "{}")
    applied = _apply(session, account, chore, payload)
    governance_repo.close_chore(session, chore_uid, "resolved", account.uid, note or applied)
    audit_repo.log(session, account.org_uid, account.uid, "resolve_chore", chore_uid,
                   {"kind": chore["type"], "node": chore["node_uid"], "result": applied})
    return {"status": "resolved", "applied": applied}


def _apply(session: Session, account: AuthedAccount, chore: dict, payload: dict) -> str:
    kind, node_uid = chore["type"], chore["node_uid"]
    if kind == "edit":
        content = payload.get("content")
        embedding = embed(f"{payload.get('title', '')}\n{content}") if content else None
        graph_repo.update_node(session, node_uid, payload, embedding)
        return "node updated"
    if kind == "invalidate":
        graph_repo.archive_node(session, node_uid)
        return "node archived (never hard-deleted)"
    if kind == "promotion":
        target = payload.get("target_topic")
        if not target:
            raise ValueError("promotion payload needs target_topic")
        topic = graph_repo.find_or_create_topic(session, account.org_uid, target, account.uid)
        graph_repo.link(session, account, topic["uid"], node_uid, "contains")
        return f"re-linked under '{topic['title']}' (origin links and scope kept)"
    if kind == "dedup_merge":
        duplicate = payload.get("duplicate_uid")
        if not duplicate:
            raise ValueError("dedup_merge payload needs duplicate_uid")
        graph_repo.archive_node(session, duplicate)
        return "duplicate archived"
    raise ValueError(f"Unknown chore type {kind}")


def approve_scope_widening(session: Session, chore_uid: str, org_uid: str, note: str) -> dict:
    """Human decision: widen a node's visibility (e.g. team -> org)."""
    chore = governance_repo.get_chore(session, org_uid, chore_uid)
    if chore is None or chore["status"] != "awaiting_human":
        raise ValueError("Chore not found or not awaiting human review")
    payload = json.loads(chore["payload"] or "{}")
    target_scope = payload.get("target_scope", "org")
    if target_scope not in ("org", "team"):
        raise ValueError("target_scope must be org or team")
    graph_repo.set_scope(session, chore["node_uid"], target_scope)
    governance_repo.close_chore(session, chore_uid, "resolved", "human-admin", note)
    audit_repo.log(session, org_uid, None, "approve_scope_widening", chore["node_uid"],
                   {"chore": chore_uid, "target_scope": target_scope})
    return {"status": "resolved", "node_uid": chore["node_uid"], "scope": target_scope}
