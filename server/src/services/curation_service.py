from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.repository import audit_repo, graph_repo
from src.services.embeddings import embed
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
