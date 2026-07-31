from __future__ import annotations

import time

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.components.config import get_settings
from src.repository import graph_repo
from src.components.embeddings import embed


def _rrf_fuse(lists: list[list[tuple[dict, float]]], k: int = 60) -> list[tuple[dict, float]]:
    """Reciprocal Rank Fusion of several ranked candidate lists → [(node, normalized_score)].
    A node's score = Σ 1/(k + rank); normalized to 0..1 so it slots in as the 'semantic' term
    alongside freshness/boosts. Rank-based, so dense cosine and BM25 scales never fight."""
    scores: dict[str, float] = {}
    nodes: dict[str, dict] = {}
    for lst in lists:
        for rank, (node, _s) in enumerate(lst):
            uid = node["uid"]
            nodes.setdefault(uid, node)
            scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank + 1)
    if not scores:
        return []
    top = max(scores.values())
    return [(nodes[uid], scores[uid] / top) for uid in scores]


def _freshness(node: dict, now_ms: float) -> float:
    """0.5 ^ (age / half_life). Convention/Decision nodes decay much slower — their value
    is their stability. Decay affects ranking only, never findability."""
    settings = get_settings()
    stable = node.get("type") in graph_repo.STABLE_TYPES
    half_life = settings.STABLE_HALF_LIFE_DAYS if stable else settings.FRESHNESS_HALF_LIFE_DAYS
    override = node.get("half_life_days")   # per-node decay override (fast for volatile topics)
    if override:
        half_life = float(override)
    age_days = max(0.0, (now_ms - node.get("last_used", now_ms)) / 86_400_000)
    return 0.5 ** (age_days / half_life)


def _worth(node: dict) -> float:
    """Outcome-based ranking shift: pos/(pos+neg) once enough samples, else neutral (0.5)."""
    settings = get_settings()
    pos, neg = node.get("pos") or 0, node.get("neg") or 0
    if pos + neg < settings.OUTCOME_MIN_SAMPLES:
        return 0.5
    return pos / (pos + neg)


def search(
    session: Session,
    account: AuthedAccount,
    query: str,
    anchors: list[str] | None = None,
    limit: int = 8,
    touch: bool = True,
    tags: list[str] | None = None,
) -> list[dict]:
    """Ranked recall: semantic similarity (when embeddings are on) combined with
    freshness. Anchors are a preference, not a filter: nodes inside the anchored topic
    subtree (the project's slice of the mind) get a ranking boost, the rest of the org's
    knowledge stays findable — knowledge from other contexts may still be the answer."""
    settings = get_settings()
    anchor_uids: set[str] = set()
    if anchors:
        anchor_uids = graph_repo.anchor_descendant_uids(session, account, anchors)

    # Hybrid retrieval: dense (vector) + sparse (BM25 full-text), fused with Reciprocal Rank
    # Fusion. Dense catches meaning; sparse catches exact tokens (symbols, error codes, paths)
    # that embeddings blur. RRF is rank-based, so the two incompatible score scales combine
    # cleanly. Falls back to word-matching only when both halves are empty.
    qvec = embed(query)
    pool = max(50, limit * 5)
    dense = graph_repo.vector_candidates(session, account, qvec, k=pool, allowed=None) if qvec else []
    sparse = graph_repo.fulltext_candidates(session, account, query, k=pool, allowed=None)
    candidates = _rrf_fuse([dense, sparse])
    if not candidates:
        candidates = graph_repo.text_candidates(session, account, query, allowed=None)

    now_ms = time.time() * 1000
    qlow = query.lower()
    want_tags = {t.strip().lower() for t in (tags or []) if t.strip()}
    scored = [
        (
            node,
            sim * settings.SEMANTIC_WEIGHT
            + _freshness(node, now_ms) * settings.FRESHNESS_WEIGHT
            + (settings.ANCHOR_BOOST if node["uid"] in anchor_uids else 0.0)
            + (settings.DECISION_BOOST if node.get("type") == "decision" else 0.0)
            + (settings.LEARNING_BOOST if node.get("type") == "learning" else 0.0)
            # tags count in search: a nudge when one of the node's tags appears in the query
            + (settings.TAG_BOOST if any(t in qlow for t in (node.get("tags") or [])) else 0.0)
            # superseded facts stay findable but drop far below the current truth
            - (settings.SUPERSEDE_PENALTY if node.get("superseded_by") else 0.0)
            # Bloom: mature/validated knowledge rises above unconfirmed 'captured' notes.
            # Unset lifecycle (legacy nodes) is neutral (0.0).
            + settings.BLOOM_BOOST.get(node.get("lifecycle"), 0.0)
            # Importance pin (0.5 neutral) + causal outcome-worth (did it actually help).
            + settings.IMPORTANCE_WEIGHT * ((node.get("importance") if node.get("importance") is not None else 0.5) - 0.5)
            + settings.OUTCOME_WEIGHT * (_worth(node) - 0.5),
        )
        for node, sim in candidates
    ]
    # explicit tag filter: keep only nodes carrying ALL requested tags
    if want_tags:
        scored = [(n, s) for n, s in scored if want_tags.issubset(set(n.get("tags") or []))]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top = []
    for node, sc in scored[:limit]:
        node["_score"] = sc   # carried so the recall hook can relevance-cap + position-order
        top.append(node)

    breadcrumbs = graph_repo.parent_titles(session, [n["uid"] for n in top])
    for node in top:
        node["topics"] = breadcrumbs.get(node["uid"], [])
    if touch:
        graph_repo.touch_nodes(session, [n["uid"] for n in top])
    return top


_STEP_ICON = {"done": "✓", "current": "▶", "open": "○"}


def render_focus(focus: dict) -> str:
    """Render the active focus as a compact, unmissable block. Injected FIRST on every
    prompt so the goal, plan and guardrails stay in the high-attention zone and survive
    compaction — the antidote to mid-session drift."""
    lines = [f"**Doel:** {focus.get('goal', '').strip()}"]
    steps = focus.get("steps") or []
    if steps:
        lines.append("**Stappen:**")
        for i, s in enumerate(steps, 1):
            icon = _STEP_ICON.get(s.get("status"), "○")
            lines.append(f"  {icon} {i}. {s.get('text', '')}")
    guardrails = focus.get("guardrails") or []
    if guardrails:
        lines.append("**Guardrails (niet afwijken):**")
        lines += [f"  - {g}" for g in guardrails]
    if focus.get("done_when"):
        lines.append(f"**Klaar wanneer:** {focus['done_when']}")
    notes = focus.get("notes") or []
    if notes:
        lines.append("**Laatste voortgang:** " + notes[-1])
    lines.append("_Herlees dit vóór elke stap. Wijkt de vraag hiervan af? Meld het eerst — "
                 "ga niet zomaar iets anders doen. Werk je stap af? Update met `focus_advance`._")
    return "\n".join(lines)


def render_system(results: list[dict]) -> str:
    """Render standing (system) memories with their FULL content — these are instructions
    the model must actually follow, so they are never truncated the way search hits are."""
    blocks = []
    for node in results:
        topics = " > ".join(node.get("topics", [])) or ""
        head = f"### {node.get('title')}" + (f"  ({topics})" if topics else "")
        blocks.append(head + "\n" + (node.get("content") or "").strip())
    return "\n\n".join(blocks)


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


def cap_and_order(results: list[dict]) -> list[dict]:
    """Anti context-rot for the recall hook: keep only a few, highly-relevant memories, then
    order them so the strongest sit at the START and END of the injected block (mitigates
    'lost in the middle'). Relies on the `_score` search() attaches."""
    settings = get_settings()
    if not results:
        return results
    top_score = results[0].get("_score", 0.0)
    floor = top_score * settings.RECALL_REL_FLOOR if top_score > 0 else float("-inf")
    kept = [r for r in results if r.get("_score", 0.0) >= floor][: settings.RECALL_MAX_MEMORIES]
    # bracket the strongest at both ends: [r0, r2, r4, …, r5, r3, r1]
    return kept[0::2] + kept[1::2][::-1]
