from __future__ import annotations

import hashlib
import json

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.repository.graph_repo import VISIBLE, _acc_params

CHORE_TYPES = {"edit", "invalidate", "dedup_merge", "promotion", "scope_widening"}


def suggestion_key(chore_type: str, node_uid: str, payload: dict) -> str:
    raw = f"{chore_type}:{node_uid}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def suggest(
    session: Session,
    account: AuthedAccount,
    chore_type: str,
    node_uid: str,
    payload: dict,
    rationale: str,
    model_name: str,
    threshold: int,
) -> dict | None:
    """File (or join) a mutation suggestion. One vote per account+model; identical
    suggestions share a suggestion_key. At the threshold the chore becomes 'ready',
    except scope_widening which always escalates to a human ('awaiting_human')."""
    key = suggestion_key(chore_type, node_uid, payload)
    record = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $node_uid, org_uid: $org_uid}})
        WHERE {VISIBLE}
        MERGE (c:Chore {{org_uid: $org_uid, suggestion_key: $key}})
        ON CREATE SET c.uid = randomUUID(), c.type = $chore_type, c.status = 'open',
                      c.payload = $payload_json, c.created = timestamp()
        MERGE (c)-[:ABOUT]->(n)
        WITH c
        MATCH (a:Account {{uid: $acc_uid}})
        MERGE (a)-[v:VOTED {{model: $model_name}}]->(c)
        ON CREATE SET v.rationale = $rationale, v.at = timestamp()
        WITH c
        MATCH ()-[v:VOTED]->(c)
        WITH c, count(v) AS votes
        SET c.status = CASE
            WHEN c.status = 'open' AND votes >= $threshold THEN
                CASE WHEN c.type = 'scope_widening' THEN 'awaiting_human' ELSE 'ready' END
            ELSE c.status END
        RETURN c.uid AS uid, c.type AS type, c.status AS status, votes
        """,
        node_uid=node_uid,
        key=key,
        chore_type=chore_type,
        payload_json=json.dumps(payload),
        rationale=rationale,
        model_name=model_name or "unknown",
        threshold=threshold,
        **_acc_params(account),
    ).single()
    return dict(record) if record else None


def open_chores(session: Session, account: AuthedAccount, limit: int = 5) -> list[dict]:
    """Chores about nodes visible to this account, actionable ('ready') first."""
    result = session.run(
        f"""
        MATCH (c:Chore {{org_uid: $org_uid}})-[:ABOUT]->(n:Knowledge)
        WHERE c.status IN ['open', 'ready'] AND {VISIBLE}
        OPTIONAL MATCH ()-[v:VOTED]->(c)
        WITH c, n, count(v) AS votes
        RETURN c.uid AS uid, c.type AS type, c.status AS status, c.payload AS payload,
               votes, n.uid AS node_uid, n.title AS node_title
        ORDER BY CASE c.status WHEN 'ready' THEN 0 ELSE 1 END, c.created
        LIMIT $limit
        """,
        limit=limit,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def resolved_chores(session: Session, account: AuthedAccount, limit: int = 25) -> list[dict]:
    """Recently handled chores (applied/rejected) about nodes visible to this account —
    the 'done' side of the swarm queue for the GUI."""
    result = session.run(
        f"""
        MATCH (c:Chore {{org_uid: $org_uid}})-[:ABOUT]->(n:Knowledge)
        WHERE c.status IN ['resolved', 'rejected'] AND {VISIBLE}
        RETURN c.uid AS uid, c.type AS type, c.status AS status, c.payload AS payload,
               c.resolution AS resolution, c.resolved_by AS resolved_by,
               c.resolved AS resolved, n.uid AS node_uid, n.title AS node_title
        ORDER BY c.resolved DESC
        LIMIT $limit
        """,
        limit=limit,
        **_acc_params(account),
    )
    return [dict(r) for r in result]


def ready_count(session: Session, account: AuthedAccount) -> int:
    record = session.run(
        f"""
        MATCH (c:Chore {{org_uid: $org_uid, status: 'ready'}})-[:ABOUT]->(n:Knowledge)
        WHERE {VISIBLE}
        RETURN count(DISTINCT c) AS n
        """,
        **_acc_params(account),
    ).single()
    return record["n"] if record else 0


def get_chore(session: Session, org_uid: str, chore_uid: str) -> dict | None:
    record = session.run(
        """
        MATCH (c:Chore {uid: $uid, org_uid: $org_uid})
        OPTIONAL MATCH (c)-[:ABOUT]->(n:Knowledge)
        RETURN c.uid AS uid, c.type AS type, c.status AS status, c.payload AS payload,
               n.uid AS node_uid, n.title AS node_title, n.scope AS node_scope
        """,
        uid=chore_uid,
        org_uid=org_uid,
    ).single()
    return dict(record) if record else None


def close_chore(
    session: Session, chore_uid: str, status: str, resolved_by: str, note: str
) -> None:
    session.run(
        """
        MATCH (c:Chore {uid: $uid})
        SET c.status = $status, c.resolved_by = $resolved_by,
            c.resolution = $note, c.resolved = timestamp()
        """,
        uid=chore_uid,
        status=status,
        resolved_by=resolved_by,
        note=note,
    )


def chores_by_status(session: Session, org_uid: str | None, status: str) -> list[dict]:
    result = session.run(
        """
        MATCH (c:Chore {status: $status})
        WHERE $org_uid IS NULL OR c.org_uid = $org_uid
        OPTIONAL MATCH (c)-[:ABOUT]->(n:Knowledge)
        OPTIONAL MATCH (a)-[v:VOTED]->(c)
        WITH c, n, collect({account: a.name, model: v.model, rationale: v.rationale}) AS votes
        ORDER BY c.created
        RETURN c.uid AS uid, c.type AS type, c.payload AS payload, c.org_uid AS org_uid,
               n.uid AS node_uid, n.title AS node_title, n.scope AS node_scope, votes
        """,
        org_uid=org_uid,
        status=status,
    )
    return [dict(r) for r in result]


def candidate_pollen(session: Session, account: AuthedAccount, limit: int = 25) -> list[dict]:
    """Open/ready chores ('Pollen') about visible nodes, with the node's embedding so the caller
    can pick the one most relevant to what the agent is currently doing."""
    result = session.run(
        f"""
        MATCH (c:Chore {{org_uid: $org_uid}})-[:ABOUT]->(n:Knowledge)
        WHERE c.status IN ['open', 'ready'] AND {VISIBLE}
        RETURN c.uid AS uid, c.type AS type, c.status AS status, c.payload AS payload,
               n.uid AS node_uid, n.title AS node_title, n.embedding AS embedding
        ORDER BY c.created DESC
        LIMIT $limit
        """,
        limit=limit,
        **_acc_params(account),
    )
    return [dict(r) for r in result]
