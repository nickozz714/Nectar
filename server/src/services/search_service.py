from __future__ import annotations

import time

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.components.config import get_settings
from src.repository import graph_repo
from src.components.embeddings import embed
from src.components import reranker


def _rerank(query: str, candidates: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    """Rewrite the base relevance of the top-K candidates with cross-encoder scores (normalized
    0..1); non-reranked candidates keep a demoted base so they stay below. The downstream blend
    still layers freshness/importance/Bloom/worth on top, so governance signals are preserved.
    No-op when reranking is disabled/unavailable."""
    settings = get_settings()
    if not settings.RERANK_ENABLED or len(candidates) < 2:
        return candidates
    ranked = sorted(candidates, key=lambda c: c[1], reverse=True)
    head, tail = ranked[:settings.RERANK_TOP_K], ranked[settings.RERANK_TOP_K:]
    docs = [f"{n.get('title', '')}\n{(n.get('content') or '')[:600]}" for n, _ in head]
    scores = reranker.rerank(query, docs)
    if scores is None or len(scores) != len(head):
        return candidates
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    new_head = [(head[i][0], (scores[i] - lo) / span) for i in range(len(head))]
    new_tail = [(n, min(s, 0.4) * 0.5) for n, s in tail]
    return new_head + new_tail


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


# ---- Ranking = dot(features, weights). The weights are the hand-tuned defaults until a
# ---- learning-to-rank model is trained from feedback (then those weights take over). ----
FEATURE_KEYS = ("sim", "freshness", "anchor", "decision", "learning", "tag",
                "superseded", "bloom", "importance", "worth", "pagerank")


def _features(node: dict, sim: float, now_ms: float, anchor_uids: set, qlow: str) -> dict:
    s = get_settings()
    return {
        "sim": sim,
        "freshness": _freshness(node, now_ms),
        "anchor": 1.0 if node["uid"] in anchor_uids else 0.0,
        "decision": 1.0 if node.get("type") == "decision" else 0.0,
        "learning": 1.0 if node.get("type") == "learning" else 0.0,
        "tag": 1.0 if any(t in qlow for t in (node.get("tags") or [])) else 0.0,
        "superseded": 1.0 if node.get("superseded_by") else 0.0,
        "bloom": s.BLOOM_BOOST.get(node.get("lifecycle"), 0.0),
        "importance": (node.get("importance") if node.get("importance") is not None else 0.5) - 0.5,
        "worth": _worth(node) - 0.5,
        "pagerank": node.get("pagerank") or 0.0,
    }


def _default_weights() -> tuple[dict, float]:
    s = get_settings()
    return ({"sim": s.SEMANTIC_WEIGHT, "freshness": s.FRESHNESS_WEIGHT, "anchor": s.ANCHOR_BOOST,
             "decision": s.DECISION_BOOST, "learning": s.LEARNING_BOOST, "tag": s.TAG_BOOST,
             "superseded": -s.SUPERSEDE_PENALTY, "bloom": 1.0, "importance": s.IMPORTANCE_WEIGHT,
             "worth": s.OUTCOME_WEIGHT, "pagerank": s.PAGERANK_WEIGHT}, 0.0)


def _apply(feat: dict, weights: dict, bias: float) -> float:
    return sum(weights.get(k, 0.0) * feat[k] for k in FEATURE_KEYS) + bias


def _ranker(session, org_uid: str) -> tuple[dict, float]:
    """Learned weights if a ranker has been trained (learning-to-rank), else the hand-tuned defaults."""
    if get_settings().LTR_ENABLED:
        learned = graph_repo.get_ranker_weights(session, org_uid)
        if learned and learned.get("weights"):
            return learned["weights"], learned.get("bias", 0.0)
    return _default_weights()


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
    # Multi-hop expansion: pull the 1-hop neighbours of the strongest anchors — the answer
    # often lives one edge away (a decision links to its rationale / superseding decision).
    # Neighbours enter at a demoted base score, so they only surface if freshness/importance lifts them.
    if candidates:
        top = sorted(candidates, key=lambda c: c[1], reverse=True)[:settings.MULTIHOP_ANCHORS]
        present = {n["uid"] for n, _ in candidates}
        for nb in graph_repo.neighbors_for(session, account, [n["uid"] for n, _ in top]):
            if nb["uid"] not in present:
                candidates.append((nb, settings.MULTIHOP_BASE))
                present.add(nb["uid"])
    # Second-stage precision: rerank the strongest candidates with a local cross-encoder, which
    # judges query+document together far more accurately than the first-stage vectors.
    candidates = _rerank(query, candidates)

    now_ms = time.time() * 1000
    qlow = query.lower()
    want_tags = {t.strip().lower() for t in (tags or []) if t.strip()}
    # Ranking is a dot product of a fixed feature vector with weights. The weights are the
    # hand-tuned defaults UNLESS a learning-to-rank model has been trained from feedback.
    weights, bias = _ranker(session, account.org_uid)
    scored = []
    for node, sim in candidates:
        feat = _features(node, sim, now_ms, anchor_uids, qlow)
        node["_feat"] = feat        # carried so the recall hook can log it as a training impression
        scored.append((node, _apply(feat, weights, bias)))
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


def render_focus(focus: dict, session_token: str = "") -> str:
    """Render the active focus as a compact, unmissable block. Injected FIRST on every
    prompt so the goal, plan and guardrails stay in the high-attention zone and survive
    compaction — the antidote to mid-session drift. With a session_token the update hint
    carries it, so the model keeps writing to ITS OWN lane instead of a sibling session's."""
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
    if session_token:
        update = (f'`focus_advance(session="{session_token}", completed_step=…, note=…)` — geef '
                  "`session` altijd mee, dit is JOUW baan; parallelle sessies in dit project "
                  "hebben hun eigen focus")
    else:
        update = "`focus_advance`"
    lines.append("_Herlees dit vóór elke stap. Wijkt de vraag hiervan af? Meld het eerst — "
                 "ga niet zomaar iets anders doen. Uitzondering: het aangeboden 🌼 Pollen "
                 "afhandelen telt níét als afwijken (mag ook via een background-subagent). "
                 f"Werk je stap af? Update met {update}._")
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
