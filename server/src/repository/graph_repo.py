from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount

KNOWLEDGE_TYPES = {
    "topic": "Topic",
    "memory": "Memory",
    "process": "Process",
    "workflow": "Workflow",
    "skill": "Skill",
    "convention": "Convention",
    "decision": "Decision",
    "glossary": "Glossary",
    "learning": "Learning",
}
# Learnings and conventions/decisions are durable — their value is stability, so they decay slowly.
STABLE_TYPES = {"convention", "decision", "learning"}

# Visibility: org-wide, own team, or own account. Comparisons with NULL are falsy in Cypher.
VISIBLE = (
    "(n.scope = 'org' "
    "OR (n.scope = 'team' AND n.team_uid = $acc_team) "
    "OR (n.scope = 'account' AND n.account_uid = $acc_uid))"
)


def _acc_params(account: AuthedAccount) -> dict:
    return {"org_uid": account.org_uid, "acc_team": account.team_uid, "acc_uid": account.uid}


def node_to_dict(node) -> dict:
    data = dict(node)
    data.pop("embedding", None)
    data["labels"] = [l for l in node.labels if l != "Knowledge"]
    return data


def anchor_descendant_uids(session: Session, account: AuthedAccount, anchors: list[str]) -> set[str]:
    """Resolve anchor topic titles to the set of uids of the topics and all their descendants."""
    result = session.run(
        """
        MATCH (t:Topic {org_uid: $org_uid})
        WHERE toLower(t.title) IN $titles
        MATCH (t)-[:CONTAINS*0..]->(n:Knowledge)
        RETURN DISTINCT n.uid AS uid
        """,
        titles=[a.strip().lower() for a in anchors if a.strip()],
        **_acc_params(account),
    )
    return {r["uid"] for r in result}


def vector_candidates(
    session: Session, account: AuthedAccount, qvec: list[float], k: int, allowed: list[str] | None
) -> list[tuple[dict, float]]:
    result = session.run(
        f"""
        CALL db.index.vector.queryNodes('knowledge_embedding', $k, $qvec)
        YIELD node AS n, score
        WHERE n.org_uid = $org_uid AND coalesce(n.archived, false) = false AND {VISIBLE}
          AND ($allowed IS NULL OR n.uid IN $allowed)
        RETURN n, score
        """,
        k=k,
        qvec=qvec,
        allowed=allowed,
        **_acc_params(account),
    )
    return [(node_to_dict(r["n"]), float(r["score"])) for r in result]


def text_candidates(
    session: Session, account: AuthedAccount, query: str, allowed: list[str] | None, limit: int = 50
) -> list[tuple[dict, float]]:
    """Fallback when embeddings are off: word-based matching, ranked by hit ratio."""
    words = [w for w in query.lower().split() if len(w) > 2]
    if not words:
        words = [query.lower()]
    result = session.run(
        f"""
        MATCH (n:Knowledge {{org_uid: $org_uid}})
        WHERE coalesce(n.archived, false) = false AND {VISIBLE}
          AND ($allowed IS NULL OR n.uid IN $allowed)
        WITH n, size([w IN $words WHERE toLower(n.title) CONTAINS w
                                     OR toLower(n.content) CONTAINS w]) AS hits
        WHERE hits > 0
        RETURN n, toFloat(hits) / size($words) AS score
        ORDER BY score DESC LIMIT $limit
        """,
        words=words,
        allowed=allowed,
        limit=limit,
        **_acc_params(account),
    )
    return [(node_to_dict(r["n"]), float(r["score"])) for r in result]


def touch_nodes(session: Session, uids: list[str]) -> None:
    """Touch-on-read: every retrieval rejuvenates the memory."""
    if not uids:
        return
    session.run(
        """
        MATCH (n:Knowledge) WHERE n.uid IN $uids
        SET n.last_used = timestamp(), n.use_count = coalesce(n.use_count, 0) + 1
        """,
        uids=uids,
    )


def get_node(session: Session, account: AuthedAccount, uid: str) -> dict | None:
    record = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $uid, org_uid: $org_uid}})
        WHERE {VISIBLE}
        OPTIONAL MATCH (p:Knowledge)-[:CONTAINS]->(n)
        OPTIONAL MATCH (n)-[:CONTAINS]->(c:Knowledge)
        OPTIONAL MATCH (n)-[:RELATES]-(r:Knowledge)
        RETURN n,
               [x IN collect(DISTINCT p) | {{uid: x.uid, title: x.title}}] AS parents,
               [x IN collect(DISTINCT c) | {{uid: x.uid, title: x.title}}] AS children,
               [x IN collect(DISTINCT r) | {{uid: x.uid, title: x.title}}] AS related
        """,
        uid=uid,
        **_acc_params(account),
    ).single()
    if record is None:
        return None
    data = node_to_dict(record["n"])
    data["parents"] = record["parents"]
    data["children"] = record["children"]
    data["related"] = record["related"]
    return data


def parent_titles(session: Session, uids: list[str]) -> dict[str, list[str]]:
    """Breadcrumbs: map node uid -> titles of its parent topics."""
    if not uids:
        return {}
    result = session.run(
        """
        MATCH (p:Knowledge)-[:CONTAINS]->(n:Knowledge)
        WHERE n.uid IN $uids
        RETURN n.uid AS uid, collect(p.title) AS parents
        """,
        uids=uids,
    )
    return {r["uid"]: r["parents"] for r in result}


def find_or_create_topic(
    session: Session, org_uid: str, title: str, account_uid: str, embedding: list[float] | None = None
) -> dict:
    record = session.run(
        """
        MERGE (t:Topic:Knowledge {org_uid: $org_uid, title_key: toLower($title)})
        ON CREATE SET t.uid = randomUUID(), t.title = $title, t.type = 'topic',
                      t.scope = 'org', t.content = '', t.archived = false,
                      t.created = timestamp(), t.last_used = timestamp(), t.use_count = 0,
                      t.created_by = $account_uid, t.embedding = $embedding, t.was_created = true
        WITH t, coalesce(t.was_created, false) AS created_now
        REMOVE t.was_created
        RETURN t.uid AS uid, t.title AS title, created_now
        """,
        org_uid=org_uid,
        title=title.strip(),
        account_uid=account_uid,
        embedding=embedding,
    ).single()
    return {"uid": record["uid"], "title": record["title"], "created": record["created_now"]}


def find_similar_topic(
    session: Session, account: AuthedAccount, embedding: list[float], threshold: float
) -> dict | None:
    """Semantic near-match against existing topic titles — prevents topic sprawl."""
    record = session.run(
        f"""
        CALL db.index.vector.queryNodes('knowledge_embedding', 5, $qvec)
        YIELD node AS n, score
        WHERE n:Topic AND n.org_uid = $org_uid AND coalesce(n.archived, false) = false
          AND {VISIBLE} AND score >= $threshold
        RETURN n.uid AS uid, n.title AS title, score
        ORDER BY score DESC LIMIT 1
        """,
        qvec=embedding,
        threshold=threshold,
        **_acc_params(account),
    ).single()
    return dict(record) if record else None


def get_artifact_by_title(
    session: Session, account: AuthedAccount, type_: str, title: str
) -> dict | None:
    label = KNOWLEDGE_TYPES[type_]
    record = session.run(
        f"""
        MATCH (n:{label} {{org_uid: $org_uid}})
        WHERE toLower(n.title) = toLower($title) AND coalesce(n.archived, false) = false
          AND {VISIBLE}
        RETURN n.uid AS uid, n.title AS title, n.created_by AS created_by
        """,
        title=title.strip(),
        **_acc_params(account),
    ).single()
    return dict(record) if record else None


def replace_skill_files(session: Session, node_uid: str, files: list[dict]) -> None:
    session.run(
        "MATCH (:Knowledge {uid: $uid})-[:HAS_FILE]->(f:SkillFile) DETACH DELETE f",
        uid=node_uid,
    )
    session.run(
        """
        MATCH (n:Knowledge {uid: $uid})
        UNWIND $files AS file
        CREATE (n)-[:HAS_FILE]->(:SkillFile {path: file.path, content: file.content})
        """,
        uid=node_uid,
        files=files,
    )


def create_knowledge(
    session: Session,
    account: AuthedAccount,
    type_: str,
    title: str,
    content: str,
    scope: str,
    embedding: list[float] | None,
    created_by_model: str = "",
    sensitivity: str = "intern",
) -> dict:
    label = KNOWLEDGE_TYPES[type_]
    record = session.run(
        f"""
        CREATE (n:Knowledge:{label} {{
            uid: randomUUID(), org_uid: $org_uid, type: $type, title: $title,
            content: $content, scope: $scope,
            team_uid: CASE WHEN $scope = 'team' THEN $acc_team ELSE NULL END,
            account_uid: CASE WHEN $scope = 'account' THEN $acc_uid ELSE NULL END,
            archived: false, created: timestamp(), last_used: timestamp(),
            use_count: 0, created_by: $acc_uid, created_by_model: $created_by_model,
            sensitivity: $sensitivity
        }})
        SET n.embedding = $embedding
        RETURN n.uid AS uid
        """,
        type=type_,
        title=title,
        content=content,
        scope=scope,
        embedding=embedding,
        created_by_model=created_by_model,
        sensitivity=sensitivity,
        **_acc_params(account),
    ).single()
    return {"uid": record["uid"]}


def link(
    session: Session, account: AuthedAccount, parent_uid: str, child_uid: str, relation: str
) -> bool:
    rel = "CONTAINS" if relation == "contains" else "RELATES"
    if rel == "CONTAINS":
        cycle = session.run(
            """
            MATCH (c:Knowledge {uid: $child_uid})-[:CONTAINS*1..]->(p:Knowledge {uid: $parent_uid})
            RETURN c LIMIT 1
            """,
            parent_uid=parent_uid,
            child_uid=child_uid,
        ).single()
        if cycle is not None:
            raise ValueError("Refused: this link would create a cycle in the topic graph")
    record = session.run(
        f"""
        MATCH (p:Knowledge {{uid: $parent_uid, org_uid: $org_uid}})
        MATCH (c:Knowledge {{uid: $child_uid, org_uid: $org_uid}})
        MERGE (p)-[r:{rel}]->(c)
        ON CREATE SET r.created = timestamp(), r.created_by = $acc_uid
        RETURN p.uid AS uid
        """,
        parent_uid=parent_uid,
        child_uid=child_uid,
        **_acc_params(account),
    ).single()
    return record is not None


def update_node(session: Session, uid: str, fields: dict, embedding: list[float] | None) -> bool:
    allowed = {k: v for k, v in fields.items() if k in ("title", "content") and v is not None}
    record = session.run(
        """
        MATCH (n:Knowledge {uid: $uid})
        SET n += $fields, n.updated = timestamp(),
            n.embedding = CASE WHEN $embedding IS NULL THEN n.embedding ELSE $embedding END
        RETURN n.uid AS uid
        """,
        uid=uid,
        fields=allowed,
        embedding=embedding,
    ).single()
    return record is not None


def nodes_for_reclassify(session: Session, org_uid: str) -> list[dict]:
    """All non-topic knowledge nodes with the text needed to recompute sensitivity."""
    result = session.run(
        """
        MATCH (n:Knowledge {org_uid: $org_uid})
        WHERE n.type <> 'topic'
        RETURN n.uid AS uid, n.title AS title, n.content AS content,
               coalesce(n.sensitivity, 'intern') AS sensitivity
        """,
        org_uid=org_uid,
    )
    return [dict(r) for r in result]


def nodes_brief(session: Session, org_uid: str) -> list[dict]:
    """Lightweight listing of all non-topic knowledge nodes (uid/title/type/tags) — for
    bulk operations like auto-tagging. Topic breadcrumbs are added by the caller."""
    result = session.run(
        """
        MATCH (n:Knowledge {org_uid: $org_uid})
        WHERE n.type <> 'topic' AND coalesce(n.archived, false) = false
        RETURN n.uid AS uid, n.title AS title, n.type AS type,
               coalesce(n.tags, []) AS tags
        ORDER BY n.type, n.title
        """,
        org_uid=org_uid,
    )
    return [dict(r) for r in result]


def set_sensitivity(session: Session, uid: str, value: str) -> bool:
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid}) SET n.sensitivity = $v RETURN n.uid AS uid",
        uid=uid, v=value,
    ).single()
    return record is not None


def set_tags(session: Session, org_uid: str, uid: str, tags: list[str]) -> bool:
    """Replace a node's tags (stored lowercased, deduped, as a native string list)."""
    clean = sorted({t.strip().lower() for t in tags if t and t.strip()})
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid, org_uid: $org_uid}) SET n.tags = $tags RETURN n.uid AS uid",
        uid=uid, org_uid=org_uid, tags=clean,
    ).single()
    return record is not None


def get_topic_by_title(session: Session, org_uid: str, title: str) -> dict | None:
    record = session.run(
        "MATCH (t:Topic {org_uid: $org_uid, title_key: toLower($title)}) "
        "RETURN t.uid AS uid, t.title AS title",
        org_uid=org_uid, title=title.strip(),
    ).single()
    return dict(record) if record else None


def reparent_all_children(session: Session, org_uid: str, src_uid: str, dst_uid: str) -> int:
    """Move every child of topic `src` under topic `dst` (used when merging topics)."""
    record = session.run(
        """
        MATCH (src:Topic {uid: $src, org_uid: $org_uid})-[r:CONTAINS]->(c:Knowledge)
        MATCH (dst:Topic {uid: $dst, org_uid: $org_uid})
        WHERE c.uid <> dst.uid
        MERGE (dst)-[:CONTAINS]->(c)
        DELETE r
        RETURN count(c) AS moved
        """,
        org_uid=org_uid, src=src_uid, dst=dst_uid,
    ).single()
    return record["moved"] if record else 0


def unlink(session: Session, org_uid: str, parent_uid: str, child_uid: str) -> int:
    """Remove the CONTAINS/RELATES edge from parent to child (a specific link only, so other
    parents/relations are kept). Returns how many edges were removed."""
    record = session.run(
        """
        MATCH (p:Knowledge {uid: $p, org_uid: $org_uid})-[r:CONTAINS|RELATES]->(c:Knowledge {uid: $c})
        DELETE r
        RETURN count(r) AS n
        """,
        p=parent_uid, c=child_uid, org_uid=org_uid,
    ).single()
    return record["n"] if record else 0


def detach_topic_parents(session: Session, org_uid: str, node_uid: str) -> int:
    """Remove the CONTAINS edges from any TOPIC parents to this node (used when moving a
    node to a different topic). Non-topic CONTAINS/RELATES links are left untouched."""
    record = session.run(
        """
        MATCH (t:Topic {org_uid: $org_uid})-[r:CONTAINS]->(n:Knowledge {uid: $uid})
        DELETE r
        RETURN count(r) AS removed
        """,
        org_uid=org_uid, uid=node_uid,
    ).single()
    return record["removed"] if record else 0


def archive_node(session: Session, uid: str) -> bool:
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid}) SET n.archived = true RETURN n.uid AS uid", uid=uid
    ).single()
    return record is not None


def hard_delete(session: Session, org_uid: str, uid: str) -> bool:
    """Permanently remove a node plus its attached files and any chores about it. The
    org_admin escape hatch from consensus-gated mutation."""
    record = session.run(
        """
        MATCH (n:Knowledge {uid: $uid, org_uid: $org_uid})
        OPTIONAL MATCH (n)-[:HAS_FILE]->(f:SkillFile)
        OPTIONAL MATCH (c:Pollen)-[:ABOUT]->(n)
        WITH n, collect(DISTINCT f) AS files, collect(DISTINCT c) AS chores
        FOREACH (x IN files | DETACH DELETE x)
        FOREACH (x IN chores | DETACH DELETE x)
        DETACH DELETE n
        RETURN 1 AS ok
        """,
        uid=uid,
        org_uid=org_uid,
    ).single()
    return record is not None


def set_system(session: Session, org_uid: str, uid: str, on: bool) -> bool:
    """Mark/unmark a node as a SYSTEM memory — always injected into recall (standing
    instructions), regardless of query relevance."""
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid, org_uid: $org_uid}) SET n.system = $on RETURN n.uid AS uid",
        uid=uid,
        org_uid=org_uid,
        on=on,
    ).single()
    return record is not None


def list_system(session: Session, account: AuthedAccount) -> list[dict]:
    """All visible SYSTEM memories, with topic breadcrumbs. Always shown in recall."""
    result = session.run(
        f"""
        MATCH (n:Knowledge {{org_uid: $org_uid}})
        WHERE n.system = true AND coalesce(n.archived, false) = false AND {VISIBLE}
        RETURN n
        ORDER BY n.type, n.title
        """,
        **_acc_params(account),
    )
    nodes = [node_to_dict(r["n"]) for r in result]
    breadcrumbs = parent_titles(session, [n["uid"] for n in nodes])
    for n in nodes:
        n["topics"] = breadcrumbs.get(n["uid"], [])
    return nodes


def upsert_system_seed(
    session: Session, org_uid: str, seed_key: str, type_: str, title: str, content: str
) -> dict:
    """Idempotently maintain a repo-seeded SYSTEM memory for an org (always in recall).
    Keyed by `seed_key` so redeploys refresh content in place. To avoid a duplicate, a
    pre-existing hand-made system node with the same title (no seed_key yet) is adopted."""
    label = KNOWLEDGE_TYPES[type_]
    # Adopt a legacy hand-made system node with this exact title so we update it in place.
    session.run(
        """
        MATCH (n:Knowledge {org_uid: $org_uid, title: $title})
        WHERE n.system = true AND n.seed_key IS NULL
        SET n.seed_key = $seed_key
        """,
        org_uid=org_uid, title=title, seed_key=seed_key,
    )
    record = session.run(
        f"""
        MERGE (n:Knowledge {{org_uid: $org_uid, seed_key: $seed_key}})
        ON CREATE SET n.uid = randomUUID(), n.created = timestamp(), n.use_count = 0,
                      n.created_by = 'system-seed', n.created_by_model = 'repo-seed'
        SET n:{label}, n.type = $type, n.title = $title, n.content = $content,
            n.scope = 'org', n.team_uid = NULL, n.account_uid = NULL,
            n.system = true, n.archived = false, n.sensitivity = 'intern',
            n.last_used = timestamp(), n.updated = timestamp()
        RETURN n.uid AS uid, n.title AS title
        """,
        org_uid=org_uid, seed_key=seed_key, type=type_, title=title, content=content,
    ).single()
    return dict(record)


def set_scope(session: Session, uid: str, target_scope: str) -> bool:
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid}) SET n.scope = $scope RETURN n.uid AS uid",
        uid=uid,
        scope=target_scope,
    ).single()
    return record is not None


def list_topics(session: Session, account: AuthedAccount) -> list[dict]:
    result = session.run(
        f"""
        MATCH (n:Topic {{org_uid: $org_uid}})
        WHERE coalesce(n.archived, false) = false AND {VISIBLE}
        OPTIONAL MATCH (n)-[:CONTAINS]->(c:Knowledge)
        RETURN n.uid AS uid, n.title AS title, count(c) AS children
        ORDER BY n.title
        """,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def topic_edges(session: Session, account: AuthedAccount) -> list[dict]:
    """CONTAINS edges between topics (for the GUI's topic overview graph)."""
    result = session.run(
        """
        MATCH (a:Topic {org_uid: $org_uid})-[:CONTAINS]->(b:Topic {org_uid: $org_uid})
        RETURN a.uid AS parent, b.uid AS child
        """,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def neighbors(session: Session, account: AuthedAccount, uid: str) -> dict:
    """A node plus its direct graph neighborhood (for click-to-expand in the GUI)."""
    result = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $uid, org_uid: $org_uid}})
        WHERE {VISIBLE}
        OPTIONAL MATCH (n)-[r]-(m:Knowledge)
        WHERE type(r) IN ['CONTAINS', 'RELATES'] AND coalesce(m.archived, false) = false
          AND (m.scope = 'org' OR (m.scope = 'team' AND m.team_uid = $acc_team)
               OR (m.scope = 'account' AND m.account_uid = $acc_uid))
        RETURN n,
               collect(DISTINCT {{uid: m.uid, title: m.title, type: m.type,
                                  relation: type(r),
                                  direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END}}) AS nbrs
        """,
        uid=uid,
        **_acc_params(account),
    ).single()
    if result is None:
        return {}
    node = node_to_dict(result["n"])
    node["neighbors"] = [x for x in result["nbrs"] if x["uid"] is not None]
    return node


def account_info(session: Session, uid: str | None) -> dict:
    if not uid:
        return {"name": None, "person": None}
    record = session.run(
        "MATCH (a:Account {uid: $uid}) RETURN a.name AS name, a.person AS person", uid=uid
    ).single()
    return dict(record) if record else {"name": None, "person": None}


def governance_rows(session: Session, account: AuthedAccount) -> list[dict]:
    """Per visible node: the classification facets for the governance dashboard."""
    result = session.run(
        f"""
        MATCH (n:Knowledge {{org_uid: $org_uid}})
        WHERE coalesce(n.archived, false) = false AND {VISIBLE}
        RETURN n.uid AS uid, n.title AS title, n.type AS type, n.scope AS scope,
               coalesce(n.sensitivity, 'intern') AS sensitivity,
               coalesce(n.created_by_model, '') AS model
        """,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def chore_status_counts(session: Session, org_uid: str) -> dict:
    result = session.run(
        "MATCH (c:Pollen {org_uid: $org_uid}) RETURN c.status AS status, count(c) AS n",
        org_uid=org_uid,
    )
    return {r["status"]: r["n"] for r in result}


def list_skills(session: Session, account: AuthedAccount) -> list[dict]:
    result = session.run(
        f"""
        MATCH (n:Skill {{org_uid: $org_uid}})
        WHERE coalesce(n.archived, false) = false AND {VISIBLE}
        RETURN n.uid AS uid, n.title AS title
        ORDER BY n.title
        """,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def node_files(session: Session, account: AuthedAccount, node_uid: str) -> list[dict]:
    """Attached files of any knowledge node (skills, workflows, ...)."""
    result = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $uid, org_uid: $org_uid}})
        WHERE {VISIBLE}
        MATCH (n)-[:HAS_FILE]->(f:SkillFile)
        RETURN f.path AS path, f.content AS content
        """,
        uid=node_uid,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def homeless_candidates(session: Session, org_uid: str) -> list[dict]:
    """Every non-topic knowledge node with the titles of its topic parents. A node with no
    topic parent (or only generic 'Overig …' buckets) is a tidy candidate: it should be
    filed under a real topic. Returns embeddings so a caller can pick the nearest topic."""
    rows = session.run(
        """
        MATCH (n:Knowledge {org_uid: $o})
        WHERE n.type <> 'topic' AND coalesce(n.archived, false) = false
        OPTIONAL MATCH (t:Knowledge {org_uid: $o})-[:CONTAINS]->(n)
        WHERE t.type = 'topic'
        WITH n, collect(t.title) AS topics
        RETURN n.uid AS uid, n.title AS title, n.type AS type,
               n.embedding AS embedding, topics AS topics
        """,
        o=org_uid,
    )
    return [dict(r) for r in rows]


def topic_embeddings(session: Session, org_uid: str) -> list[dict]:
    """All topics with their embedding vectors (for nearest-topic matching)."""
    rows = session.run(
        """
        MATCH (t:Knowledge {org_uid: $o}) WHERE t.type = 'topic'
        RETURN t.uid AS uid, t.title AS title, t.embedding AS embedding
        """,
        o=org_uid,
    )
    return [dict(r) for r in rows]


def topic_member_embeddings(session: Session, org_uid: str) -> list[dict]:
    """(topic_uid, embedding) for every non-topic node a topic directly CONTAINS — so a caller
    can build each topic's semantic centroid (a far better 'home' signal than the title alone)."""
    rows = session.run(
        """
        MATCH (t:Knowledge {org_uid: $o})-[:CONTAINS]->(n:Knowledge {org_uid: $o})
        WHERE t.type = 'topic' AND n.type <> 'topic' AND n.embedding IS NOT NULL
        RETURN t.uid AS topic_uid, n.embedding AS embedding
        """,
        o=org_uid,
    )
    return [dict(r) for r in rows]


import re as _re


def fulltext_candidates(
    session: Session, account: AuthedAccount, query: str, k: int, allowed: list[str] | None
) -> list[tuple[dict, float]]:
    """BM25 hits from the Lucene full-text index — the sparse half of hybrid retrieval. Terms
    are OR-ed and Lucene-escaped so exact identifiers match without breaking the parser."""
    terms = _re.findall(r"\w+", query.lower())
    if not terms:
        return []
    lucene = " OR ".join(terms)
    try:
        result = session.run(
            f"""
            CALL db.index.fulltext.queryNodes('knowledge_fulltext', $q) YIELD node AS n, score
            WHERE n.org_uid = $org_uid AND coalesce(n.archived, false) = false AND {VISIBLE}
              AND ($allowed IS NULL OR n.uid IN $allowed)
            RETURN n, score ORDER BY score DESC LIMIT $k
            """,
            q=lucene, k=k, allowed=allowed, **_acc_params(account),
        )
        return [(node_to_dict(r["n"]), float(r["score"])) for r in result]
    except Exception:  # index still building / unavailable → sparse half simply contributes nothing
        return []
