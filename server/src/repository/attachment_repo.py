from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.repository.graph_repo import VISIBLE, _acc_params

# Artifacts (exports, scripts, screenshots, …) referenced by a memory often live only on the
# machine that added them. Attachments store the bytes centrally in the hive (a :Attachment
# node, base64 in Neo4j — single store, travels in the backup) linked to the owning knowledge
# node, so any machine can fetch them on demand. They are NOT injected into recall.


def add(
    session: Session, account: AuthedAccount, node_uid: str,
    filename: str, content_type: str, data_b64: str, size: int, sha256: str,
) -> dict | None:
    """Attach a file to a node the caller can see. Returns the attachment metadata."""
    record = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $node_uid, org_uid: $org_uid}})
        WHERE {VISIBLE}
        CREATE (a:Attachment {{uid: randomUUID(), org_uid: $org_uid, node_uid: $node_uid,
            filename: $filename, content_type: $content_type, size: $size, sha256: $sha256,
            data: $data, created: timestamp(), created_by: $acc_uid}})
        CREATE (n)-[:HAS_ATTACHMENT]->(a)
        RETURN a.uid AS uid, a.filename AS filename, a.content_type AS content_type,
               a.size AS size, a.sha256 AS sha256, a.created AS created
        """,
        node_uid=node_uid, filename=filename, content_type=content_type,
        size=size, sha256=sha256, data=data_b64, **_acc_params(account),
    ).single()
    return dict(record) if record else None


def list_for(session: Session, account: AuthedAccount, node_uid: str) -> list[dict]:
    """Attachment metadata (no bytes) for a visible node."""
    result = session.run(
        f"""
        MATCH (n:Knowledge {{uid: $node_uid, org_uid: $org_uid}})-[:HAS_ATTACHMENT]->(a:Attachment)
        WHERE {VISIBLE}
        RETURN a.uid AS uid, a.filename AS filename, a.content_type AS content_type,
               a.size AS size, a.sha256 AS sha256, a.created AS created
        ORDER BY a.created
        """,
        node_uid=node_uid, **_acc_params(account),
    )
    return [dict(r) for r in result]


def get(session: Session, account: AuthedAccount, att_uid: str) -> dict | None:
    """Fetch one attachment WITH its bytes — only if the owning node is visible."""
    record = session.run(
        f"""
        MATCH (n:Knowledge {{org_uid: $org_uid}})-[:HAS_ATTACHMENT]->(a:Attachment {{uid: $uid}})
        WHERE {VISIBLE}
        RETURN a.filename AS filename, a.content_type AS content_type, a.data AS data,
               a.size AS size, a.node_uid AS node_uid
        """,
        uid=att_uid, **_acc_params(account),
    ).single()
    return dict(record) if record else None


def delete(session: Session, account: AuthedAccount, att_uid: str) -> str | None:
    """Delete an attachment on a visible node. Returns its owning node uid, or None."""
    record = session.run(
        f"""
        MATCH (n:Knowledge {{org_uid: $org_uid}})-[:HAS_ATTACHMENT]->(a:Attachment {{uid: $uid}})
        WHERE {VISIBLE}
        WITH a, a.node_uid AS node_uid
        DETACH DELETE a
        RETURN node_uid
        """,
        uid=att_uid, **_acc_params(account),
    ).single()
    return record["node_uid"] if record else None
