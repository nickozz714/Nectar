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
