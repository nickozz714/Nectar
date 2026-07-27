from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount

# Per-account working-session snapshots, so a session can be handed off and resumed later,
# on any device — as long as you hold a token for the same account. NOT shared knowledge
# (separate :HiveSession label), so it never leaks into recall/search.


def save(session: Session, account: AuthedAccount, key: str, state: str) -> dict:
    record = session.run(
        """
        MERGE (s:HiveSession {account_uid: $acc, key: $key})
        ON CREATE SET s.uid = randomUUID(), s.org_uid = $org, s.created = timestamp()
        SET s.state = $state, s.updated = timestamp()
        RETURN s.uid AS uid, s.updated AS updated
        """,
        acc=account.uid,
        org=account.org_uid,
        key=key,
        state=state,
    ).single()
    return {"key": key, "uid": record["uid"], "updated": record["updated"]}


def list_for(session: Session, account: AuthedAccount) -> list[dict]:
    result = session.run(
        """
        MATCH (s:HiveSession {account_uid: $acc})
        RETURN s.key AS key, s.updated AS updated, size(coalesce(s.state, '')) AS chars
        ORDER BY s.updated DESC
        """,
        acc=account.uid,
    )
    return [dict(r) for r in result]


def get(session: Session, account: AuthedAccount, key: str) -> dict | None:
    record = session.run(
        """
        MATCH (s:HiveSession {account_uid: $acc, key: $key})
        RETURN s.key AS key, s.state AS state, s.updated AS updated
        """,
        acc=account.uid,
        key=key,
    ).single()
    return dict(record) if record else None


def delete(session: Session, account: AuthedAccount, key: str) -> bool:
    record = session.run(
        """
        MATCH (s:HiveSession {account_uid: $acc, key: $key})
        WITH s, s.key AS k
        DETACH DELETE s
        RETURN k AS ok
        """,
        acc=account.uid,
        key=key,
    ).single()
    return record is not None
