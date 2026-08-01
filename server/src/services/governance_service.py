from __future__ import annotations

import json

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.components.config import get_settings
from src.repository import audit_repo, governance_repo, graph_repo, tenancy_repo
from src.components.embeddings import embed


def suggest(
    session: Session,
    account: AuthedAccount,
    chore_type: str,
    node_uid: str,
    payload: dict,
    rationale: str,
    model_name: str,
) -> dict:
    if chore_type not in governance_repo.POLLEN_TYPES:
        raise ValueError(f"kind must be one of: {', '.join(sorted(governance_repo.POLLEN_TYPES))}")
    result = governance_repo.suggest(
        session, account, chore_type, node_uid, payload, rationale, model_name,
        threshold=tenancy_repo.get_consensus_threshold(
            session, account.org_uid, get_settings().CONSENSUS_THRESHOLD),
    )
    if result is None:
        raise ValueError("Node not found or not visible to this account")
    audit_repo.log(session, account.org_uid, account.uid, "suggest", node_uid,
                   {"kind": chore_type, "chore": result["uid"]})
    return result


def resolve(
    session: Session, account: AuthedAccount, chore_uid: str, action: str, note: str
) -> dict:
    """A bee resolves a 'ready' chore — maintainer role required, so upkeep is
    delegated deliberately instead of open to everyone. scope_widening never passes
    through here — that is the one mutation reserved for a human reviewer."""
    assert_role(account, "member", "Resolving Pollen")   # any Swarm member may pick up ready Pollen
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


def admin_resolve(
    session: Session, account: AuthedAccount, chore_uid: str, action: str, note: str
) -> dict:
    """org_admin escape hatch: resolve a chore that has NOT reached consensus ('open') or is
    'ready', directly — for small/solo orgs where the 2-vote threshold never triggers.
    Audited as a bypass. scope_widening still goes through the human review queue."""
    assert_role(account, "org_admin", "Directly resolving chores")
    chore = governance_repo.get_chore(session, account.org_uid, chore_uid)
    if chore is None:
        raise ValueError("Chore not found")
    if chore["status"] not in ("open", "ready"):
        raise ValueError(f"Chore is '{chore['status']}' — already handled")
    if chore["type"] == "scope_widening":
        raise ValueError("scope_widening is decided by a human via the admin review queue")
    if action == "reject":
        governance_repo.close_chore(session, chore_uid, "rejected", account.uid, note or "org_admin afgewezen")
        audit_repo.log(session, account.org_uid, account.uid, "admin_resolve_chore", chore_uid,
                       {"kind": chore["type"], "action": "reject", "bypass": "consensus"})
        return {"status": "rejected"}
    if action != "apply":
        raise ValueError("action must be apply or reject")

    payload = json.loads(chore["payload"] or "{}")
    applied = _apply(session, account, chore, payload)
    governance_repo.close_chore(session, chore_uid, "resolved", account.uid, note or applied)
    audit_repo.log(session, account.org_uid, account.uid, "admin_resolve_chore", chore_uid,
                   {"kind": chore["type"], "node": chore["node_uid"], "result": applied,
                    "bypass": "consensus"})
    return {"status": "resolved", "applied": applied}


def _apply(session: Session, account: AuthedAccount, chore: dict, payload: dict) -> str:
    kind, node_uid = chore["type"], chore["node_uid"]
    if kind == "edit":
        content = payload.get("content")
        embedding = embed(f"{payload.get('title', '')}\n{content}") if content else None
        graph_repo.update_node(session, node_uid, payload, embedding)
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")  # reviewed edit
        return "node updated"
    if kind == "invalidate":
        graph_repo.archive_node(session, node_uid)
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "deprecated")
        return "node archived (never hard-deleted)"
    if kind == "promotion":
        target = payload.get("target_topic")
        if not target:
            raise ValueError("promotion payload needs target_topic")
        topic = graph_repo.find_or_create_topic(session, account.org_uid, target, account.uid)
        graph_repo.link(session, account, topic["uid"], node_uid, "contains")
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")  # swarm reviewed it
        return f"re-linked under '{topic['title']}' (origin links and scope kept)"
    if kind == "dedup_merge":
        duplicate = payload.get("duplicate_uid")
        if not duplicate:
            raise ValueError("dedup_merge payload needs duplicate_uid")
        graph_repo.archive_node(session, duplicate)
        graph_repo.set_lifecycle(session, account.org_uid, duplicate, "deprecated")
        return "duplicate archived"
    if kind == "stale_review":
        # "yes, still correct" — refresh it (resets the decay clock) and confirm it as validated.
        graph_repo.touch_nodes(session, [node_uid])
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")
        return "reviewed — confirmed current"
    raise ValueError(f"Unknown chore type {kind}")


def admin_delete(session: Session, account: AuthedAccount, uid: str) -> dict:
    """org_admin escape hatch: permanently delete a knowledge node. Bypasses the
    consensus gate on purpose (humans prune), and is audited."""
    assert_role(account, "org_admin", "Deleting memories")
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    graph_repo.hard_delete(session, account.org_uid, uid)
    audit_repo.log(session, account.org_uid, account.uid, "delete", uid,
                   {"title": node.get("title"), "type": node.get("type")})
    return {"deleted": True, "uid": uid, "title": node.get("title")}


def set_system(session: Session, account: AuthedAccount, uid: str, on: bool) -> dict:
    """org_admin: mark a node as a SYSTEM memory (always injected into recall) or unmark it.
    Use for standing instructions like 'how to work with the Nectar'."""
    assert_role(account, "org_admin", "Setting system memories")
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    graph_repo.set_system(session, account.org_uid, uid, on)
    audit_repo.log(session, account.org_uid, account.uid, "set_system", uid, {"on": on})
    return {"uid": uid, "system": on, "title": node.get("title")}


def approve_scope_widening(
    session: Session, chore_uid: str, org_uid: str, note: str, reviewed_by: str = "human-admin"
) -> dict:
    """Human decision: widen a node's visibility (e.g. team -> org)."""
    chore = governance_repo.get_chore(session, org_uid, chore_uid)
    if chore is None or chore["status"] != "awaiting_human":
        raise ValueError("Chore not found or not awaiting human review")
    payload = json.loads(chore["payload"] or "{}")
    target_scope = payload.get("target_scope", "org")
    if target_scope not in ("org", "team"):
        raise ValueError("target_scope must be org or team")
    graph_repo.set_scope(session, chore["node_uid"], target_scope)
    governance_repo.close_chore(session, chore_uid, "resolved", reviewed_by, note)
    audit_repo.log(session, org_uid, None, "approve_scope_widening", chore["node_uid"],
                   {"chore": chore_uid, "target_scope": target_scope, "reviewed_by": reviewed_by})
    return {"status": "resolved", "node_uid": chore["node_uid"], "scope": target_scope}


def _cos(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


_POLLEN_VERB = {
    "promotion": "een node onder een beter topic hangen",
    "dedup_merge": "een duplicaat samenvoegen",
    "edit": "een voorgestelde tekstwijziging beoordelen",
    "invalidate": "verouderde kennis archiveren",
    "scope_widening": "een scope-verbreding beoordelen (mens)",
    "stale_review": "een oude-maar-veelgebruikte memory herbevestigen of bijwerken",
}


def pick_contextual_pollen(session: Session, account: AuthedAccount, query: str) -> dict | None:
    """Choose the single most relevant open/ready Pollen (chore) for what the agent is doing:
    rank candidates by embedding similarity between the agent's prompt and the chore's node,
    with a small boost for 'ready'. Returns the chore dict (or None if the hive has no Pollen)."""
    from src.components.embeddings import embed

    cands = governance_repo.candidate_pollen(
        session, account, limit=25, ttl_min=get_settings().CLAIM_TTL_MIN)
    if not cands:
        return None
    qv = embed(query) if query else None

    def score(c):
        sim = _cos(qv, c.get("embedding")) if qv else 0.0
        return sim + (0.15 if c["status"] == "ready" else 0.0)

    return max(cands, key=score)


def render_pollen(pollen: dict) -> str:
    """One-line instruction that hands the agent a bit of Pollen to carry."""
    import json as _json
    what = _POLLEN_VERB.get(pollen["type"], pollen["type"])
    payload = {}
    try:
        payload = _json.loads(pollen.get("payload") or "{}")
    except (ValueError, TypeError):
        pass
    target = payload.get("target_topic")
    detail = f" → voorstel: onder '{target}'" if target else ""
    node = pollen.get("node_title") or ""
    node = node[:70] + "…" if len(node) > 70 else node
    return (f"🌼 **Pollen** — draag bij aan de Hive terwijl je hier toch bent: {what} "
            f"voor *{node}*{detail}. Past het bij je taak? Beoordeel 'm op inhoud en los 'm op "
            f"met `hive_chores()` → `hive_resolve_chore(\"{pollen['uid']}\", \"apply\"|\"reject\")`.")
