from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount


def set_secret(session: Session, account: AuthedAccount, name: str, ciphertext: str) -> dict:
    """Create or update a secret; only the owner may overwrite an existing one."""
    existing = session.run(
        """
        MATCH (s:Secret {org_uid: $org_uid, name: $name})
        OPTIONAL MATCH (owner:Account)-[:OWNS]->(s)
        RETURN s.uid AS uid, owner.uid AS owner_uid
        """,
        org_uid=account.org_uid,
        name=name,
    ).single()
    if existing is not None and existing["owner_uid"] != account.uid:
        raise PermissionError("Secret exists and is owned by another account")
    record = session.run(
        """
        MATCH (a:Account {uid: $acc_uid})
        MERGE (s:Secret {org_uid: $org_uid, name: $name})
        ON CREATE SET s.uid = randomUUID(), s.created = timestamp()
        SET s.ciphertext = $ciphertext, s.updated = timestamp()
        MERGE (a)-[:OWNS]->(s)
        RETURN s.uid AS uid, s.name AS name
        """,
        org_uid=account.org_uid,
        acc_uid=account.uid,
        name=name,
        ciphertext=ciphertext,
    ).single()
    return dict(record)


def get_secret(session: Session, account: AuthedAccount, name: str) -> str | None:
    """Return the ciphertext when the account owns the secret or holds a grant."""
    record = session.run(
        """
        MATCH (s:Secret {org_uid: $org_uid, name: $name})
        MATCH (a:Account {uid: $acc_uid})
        WHERE (a)-[:OWNS]->(s) OR (a)-[:GRANTED]->(s)
        RETURN s.ciphertext AS ciphertext
        """,
        org_uid=account.org_uid,
        acc_uid=account.uid,
        name=name,
    ).single()
    return record["ciphertext"] if record else None


def grant_secret(session: Session, org_uid: str, name: str, account_uid: str) -> bool:
    record = session.run(
        """
        MATCH (s:Secret {org_uid: $org_uid, name: $name})
        MATCH (a:Account {uid: $account_uid, org_uid: $org_uid})
        MERGE (a)-[g:GRANTED]->(s)
        ON CREATE SET g.created = timestamp()
        RETURN s.uid AS uid
        """,
        org_uid=org_uid,
        name=name,
        account_uid=account_uid,
    ).single()
    return record is not None


def list_secret_names(session: Session, org_uid: str) -> list[dict]:
    result = session.run(
        """
        MATCH (s:Secret {org_uid: $org_uid})
        OPTIONAL MATCH (owner:Account)-[:OWNS]->(s)
        OPTIONAL MATCH (g:Account)-[:GRANTED]->(s)
        RETURN s.name AS name, owner.name AS owner, collect(g.name) AS granted_to
        ORDER BY s.name
        """,
        org_uid=org_uid,
    )
    return [dict(r) for r in result]
