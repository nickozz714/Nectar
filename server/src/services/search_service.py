from __future__ import annotations

import time

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.config import get_settings
from src.repository import graph_repo
from src.services.embeddings import embed


def _freshness(node: dict, now_ms: float) -> float:
    """0.5 ^ (age / half_life). Convention/Decision nodes decay much slower — their value
    is their stability. Decay affects ranking only, never findability."""
    settings = get_settings()
    stable = node.get("type") in graph_repo.STABLE_TYPES
    half_life = settings.STABLE_HALF_LIFE_DAYS if stable else settings.FRESHNESS_HALF_LIFE_DAYS
    age_days = max(0.0, (now_ms - node.get("last_used", now_ms)) / 86_400_000)
    return 0.5 ** (age_days / half_life)


def search(
    session: Session,
    account: AuthedAccount,
    query: str,
    anchors: list[str] | None = None,
    limit: int = 8,
    touch: bool = True,
) -> list[dict]:
    """Ranked recall: semantic similarity (when embeddings are on) combined with
    freshness. Anchors are a preference, not a filter: nodes inside the anchored topic
    subtree (the project's slice of the mind) get a ranking boost, the rest of the org's
    knowledge stays findable — knowledge from other contexts may still be the answer."""
    settings = get_settings()
    anchor_uids: set[str] = set()
    if anchors:
        anchor_uids = graph_repo.anchor_descendant_uids(session, account, anchors)

    qvec = embed(query)
    if qvec is not None:
        candidates = graph_repo.vector_candidates(
            session, account, qvec, k=max(50, limit * 5), allowed=None
        )
    else:
        candidates = graph_repo.text_candidates(session, account, query, allowed=None)

    now_ms = time.time() * 1000
    scored = [
        (
            node,
            sim * settings.SEMANTIC_WEIGHT
            + _freshness(node, now_ms) * settings.FRESHNESS_WEIGHT
            + (settings.ANCHOR_BOOST if node["uid"] in anchor_uids else 0.0)
            + (settings.DECISION_BOOST if node.get("type") == "decision" else 0.0),
        )
        for node, sim in candidates
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top = [node for node, _ in scored[:limit]]

    breadcrumbs = graph_repo.parent_titles(session, [n["uid"] for n in top])
    for node in top:
        node["topics"] = breadcrumbs.get(node["uid"], [])
    if touch:
        graph_repo.touch_nodes(session, [n["uid"] for n in top])
    return top


def render_results(results: list[dict]) -> str:
    if not results:
        return "No hive memories matched."
    lines = []
    for node in results:
        topics = " > ".join(node.get("topics", [])) or "(no topic)"
        snippet = (node.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:220] + "…"
        lines.append(f"- [{node.get('type')}] **{node.get('title')}** ({topics}) — {snippet} "
                     f"(uid: {node.get('uid')})")
    return "\n".join(lines)
