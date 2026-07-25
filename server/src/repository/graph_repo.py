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
}
STABLE_TYPES = {"convention", "decision"}

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
            use_count: 0, created_by: $acc_uid, created_by_model: $created_by_model
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


def archive_node(session: Session, uid: str) -> bool:
    record = session.run(
        "MATCH (n:Knowledge {uid: $uid}) SET n.archived = true RETURN n.uid AS uid", uid=uid
    ).single()
    return record is not None


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
