from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.repository import audit_repo, graph_repo
from src.components.embeddings import embed
from src.services.memory_service import classify_sensitivity


def create_topic(
    session: Session, account: AuthedAccount, title: str, parent_topic: str = ""
) -> dict:
    """Create a topic (reuses an existing one with the same title). Optionally nest it under
    a parent topic. Any member may organise the mind by adding topics."""
    title = title.strip()
    if len(title) < 2:
        raise ValueError("A topic needs a title")
    topic = graph_repo.find_or_create_topic(session, account.org_uid, title, account.uid, embed(title))
    if parent_topic.strip():
        parent = graph_repo.find_or_create_topic(
            session, account.org_uid, parent_topic.strip(), account.uid, embed(parent_topic.strip())
        )
        graph_repo.link(session, account, parent["uid"], topic["uid"], "contains")
    audit_repo.log(session, account.org_uid, account.uid, "create_topic", topic["uid"],
                   {"title": title, "parent": parent_topic or None})
    return topic


def merge_topics(
    session: Session, account: AuthedAccount, from_topic: str, into_topic: str
) -> dict:
    """Merge topic `from_topic` INTO `into_topic`: move all its children (memories, skills,
    sub-topics) under the target, then delete the now-empty source topic. Maintainer role.
    Deduplicates topics that ended up split (e.g. 'GGM' vs 'Gemeentelijk Gegevens Model')."""
    assert_role(account, "maintainer", "Merging topics")
    src = graph_repo.get_topic_by_title(session, account.org_uid, from_topic)
    if src is None:
        raise ValueError(f"Source topic '{from_topic}' not found")
    dst = graph_repo.find_or_create_topic(
        session, account.org_uid, into_topic.strip(), account.uid, embed(into_topic.strip())
    )
    if src["uid"] == dst["uid"]:
        raise ValueError("Source and target topic are the same")
    moved = graph_repo.reparent_all_children(session, account.org_uid, src["uid"], dst["uid"])
    graph_repo.hard_delete(session, account.org_uid, src["uid"])
    audit_repo.log(session, account.org_uid, account.uid, "merge_topics", dst["uid"],
                   {"from": src["title"], "into": dst["title"], "moved": moved})
    return {"into_topic": dst["title"], "merged_from": src["title"], "moved_children": moved}


def move_node(
    session: Session, account: AuthedAccount, node_uid: str, to_topic: str,
    keep_others: bool = False,
) -> dict:
    """Re-hang a node under a different topic (curation — maintainer role). By default it
    REPLACES the node's topic parents; keep_others=True just adds the new one (multi-parent).
    The target topic is created if it does not exist yet."""
    assert_role(account, "maintainer", "Moving nodes between topics")
    node = graph_repo.get_node(session, account, node_uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    if node.get("type") == "topic":
        raise ValueError("Use topic nesting for topics, not move")

    target = graph_repo.find_or_create_topic(
        session, account.org_uid, to_topic.strip(), account.uid, embed(to_topic.strip())
    )
    removed = 0
    if not keep_others:
        removed = graph_repo.detach_topic_parents(session, account.org_uid, node_uid)
    graph_repo.link(session, account, target["uid"], node_uid, "contains")  # cycle-checked
    audit_repo.log(session, account.org_uid, account.uid, "move_node", node_uid,
                   {"to_topic": target["title"], "replaced": removed, "keep_others": keep_others})
    return {"node_uid": node_uid, "to_topic": target["title"], "removed_parents": removed}


def list_nodes_brief(session: Session, account: AuthedAccount) -> list[dict]:
    """All non-topic nodes with their topic breadcrumbs and current tags."""
    nodes = graph_repo.nodes_brief(session, account.org_uid)
    crumbs = graph_repo.parent_titles(session, [n["uid"] for n in nodes])
    for n in nodes:
        n["topics"] = crumbs.get(n["uid"], [])
    return nodes


def bulk_set_tags(session: Session, account: AuthedAccount, items: list[dict]) -> dict:
    """Apply tags to many nodes at once: items = [{uid, tags}]. Maintainer role (bulk
    curation). Missing/invisible uids are skipped."""
    assert_role(account, "maintainer", "Bulk tagging")
    updated = 0
    for it in items:
        uid, tags = it.get("uid"), it.get("tags") or []
        if uid and graph_repo.set_tags(session, account.org_uid, uid, tags):
            updated += 1
    audit_repo.log(session, account.org_uid, account.uid, "bulk_set_tags", account.org_uid,
                   {"count": updated})
    return {"updated": updated}


def reclassify_sensitivity(session: Session, account: AuthedAccount) -> dict:
    """Re-run the (value-based) sensitivity classifier over every node in the org and fix
    stale labels — e.g. old keyword-based false positives that are not actually secret.
    org_admin only; audited."""
    assert_role(account, "org_admin", "Reclassifying sensitivity")
    scanned = changed = to_internal = to_sensitive = 0
    for n in graph_repo.nodes_for_reclassify(session, account.org_uid):
        scanned += 1
        want = classify_sensitivity(f"{n.get('title', '')}\n{n.get('content', '')}")
        if want != n["sensitivity"]:
            graph_repo.set_sensitivity(session, n["uid"], want)
            changed += 1
            if want == "intern":
                to_internal += 1
            else:
                to_sensitive += 1
    audit_repo.log(session, account.org_uid, account.uid, "reclassify_sensitivity", account.org_uid,
                   {"scanned": scanned, "changed": changed})
    return {"scanned": scanned, "changed": changed,
            "now_internal": to_internal, "now_sensitive": to_sensitive}


def set_tags(
    session: Session, account: AuthedAccount, node_uid: str,
    add: list[str] | None = None, remove: list[str] | None = None, replace: list[str] | None = None,
) -> dict:
    """Add/remove/replace tags on a node. Tags are lowercased and count in search ranking."""
    node = graph_repo.get_node(session, account, node_uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    if replace is not None:
        tags = set(t.lower() for t in replace)
    else:
        tags = {t.lower() for t in (node.get("tags") or [])}
        tags |= {t.strip().lower() for t in (add or []) if t.strip()}
        tags -= {t.strip().lower() for t in (remove or [])}
    graph_repo.set_tags(session, account.org_uid, node_uid, sorted(tags))
    audit_repo.log(session, account.org_uid, account.uid, "set_tags", node_uid, {"tags": sorted(tags)})
    return {"node_uid": node_uid, "tags": sorted(tags)}


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else -1.0


def _is_generic(title: str) -> bool:
    t = (title or "").strip().lower()
    return t.startswith("overig")


def tidy_scan(session: Session, account: AuthedAccount) -> dict:
    """Housekeeping: find knowledge that isn't filed under a real topic and open a `promotion`
    chore proposing the nearest topic as its home. Non-destructive by construction — resolving
    a promotion only ADDS a CONTAINS link (origin links + scope are kept, nothing is deleted).
    Idempotent: the chore's suggestion_key means re-scanning won't create duplicates. This is
    the recurring 'tidy & re-organise the hive' loop. Maintainer role."""
    assert_role(account, "maintainer", "Running the tidy scan")
    from collections import defaultdict
    from src.repository import governance_repo, tenancy_repo
    from src.components.config import get_settings

    MIN_SCORE = 0.14   # below this the best topic is a weak guess → leave the node alone

    topics = {t["uid"]: t for t in graph_repo.topic_embeddings(session, account.org_uid)
              if t.get("embedding") and not _is_generic(t["title"])}
    # A topic's semantic centre = the centroid of the nodes it already holds — a much better
    # "does this belong here?" signal than its title. Fall back to the title when it's empty.
    sums, cnt = {}, defaultdict(int)
    for m in graph_repo.topic_member_embeddings(session, account.org_uid):
        tid, e = m["topic_uid"], m["embedding"]
        if tid not in topics or not e:
            continue
        sums.setdefault(tid, [0.0] * len(e))
        for i, x in enumerate(e):
            sums[tid][i] += x
        cnt[tid] += 1
    centroid = {tid: [x / cnt[tid] for x in s] for tid, s in sums.items()}

    def score(emb, tid):
        t = topics[tid]
        s_title = _cosine(emb, t["embedding"])
        s_cent = _cosine(emb, centroid[tid]) if tid in centroid else -1.0
        return max(s_cent, 0.6 * s_title)   # members dominate; title is a fallback/boost

    candidates = graph_repo.homeless_candidates(session, account.org_uid)
    opened = []
    for n in candidates:
        if n.get("topics"):
            continue   # any topic parent (incl. a generic 'Overig' bucket) counts as filed —
                       # getting things OUT of Overig is a manual choice, not something to nag about
        emb = n.get("embedding")
        if not emb:
            continue
        best, best_s = None, MIN_SCORE
        for tid, t in topics.items():
            if t["title"] in (n.get("topics") or []):
                continue
            s = score(emb, tid)
            if s > best_s:
                best, best_s = t, s
        if best is None:
            continue   # no topic scores above the threshold → don't guess
        res = governance_repo.suggest(
            session, account, "promotion", n["uid"], {"target_topic": best["title"]},
            rationale=f"Opruim-scan: '{n['title'][:60]}' hangt niet onder een topic — "
                      f"voorgesteld huis: '{best['title']}' (score {best_s:.2f}).",
            model_name="tidy-scan", threshold=tenancy_repo.get_consensus_threshold(
                session, account.org_uid, get_settings().CONSENSUS_THRESHOLD),
        )
        if res:
            opened.append({"node": n["title"], "type": n["type"], "target": best["title"],
                           "score": round(best_s, 3), "chore": res["uid"], "status": res["status"]})
    audit_repo.log(session, account.org_uid, account.uid, "tidy_scan", account.org_uid,
                   {"scanned": len(candidates), "opened": len(opened)})
    return {"scanned": len(candidates), "homeless": len(opened), "chores": opened}
