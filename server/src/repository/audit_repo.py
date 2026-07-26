from __future__ import annotations

import json

from neo4j import Session


def log(
    session: Session,
    org_uid: str,
    account_uid: str | None,
    action: str,
    target: str,
    detail: dict | None = None,
) -> None:
    """Append-only audit trail. Every secret read and every mutation lands here."""
    session.run(
        """
        CREATE (e:Audit {uid: randomUUID(), org_uid: $org_uid, action: $action,
                         target: $target, detail: $detail, at: timestamp()})
        WITH e
        OPTIONAL MATCH (a:Account {uid: $account_uid})
        FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END | CREATE (a)-[:DID]->(e))
        """,
        org_uid=org_uid,
        account_uid=account_uid,
        action=action,
        target=target,
        detail=json.dumps(detail or {}),
    )


def events_for_target(session: Session, org_uid: str, target: str) -> list[dict]:
    """Lineage: every audit event that touched this node, oldest first."""
    result = session.run(
        """
        MATCH (e:Audit {org_uid: $org_uid, target: $target})
        OPTIONAL MATCH (a:Account)-[:DID]->(e)
        RETURN e.at AS at, e.action AS action, e.detail AS detail,
               a.name AS account, a.person AS person
        ORDER BY e.at ASC
        """,
        org_uid=org_uid,
        target=target,
    )
    return [dict(r) for r in result]


def recent(session: Session, org_uid: str, limit: int = 100) -> list[dict]:
    """Newest audit events first — the transparency window on everything that happened."""
    result = session.run(
        """
        MATCH (e:Audit {org_uid: $org_uid})
        OPTIONAL MATCH (a:Account)-[:DID]->(e)
        RETURN e.at AS at, e.action AS action, e.target AS target,
               e.detail AS detail, a.name AS account
        ORDER BY e.at DESC LIMIT $limit
        """,
        org_uid=org_uid,
        limit=limit,
    )
    return [dict(r) for r in result]
