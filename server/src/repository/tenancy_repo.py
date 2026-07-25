from __future__ import annotations

import secrets as pysecrets

from neo4j import Session

from src.authentication.deps import hash_token


def create_org(session: Session, name: str) -> dict:
    record = session.run(
        """
        CREATE (o:Org {uid: randomUUID(), name: $name, created: timestamp()})
        RETURN o.uid AS uid, o.name AS name
        """,
        name=name,
    ).single()
    return dict(record)


def create_team(session: Session, org_uid: str, name: str) -> dict | None:
    record = session.run(
        """
        MATCH (o:Org {uid: $org_uid})
        MERGE (t:Team {org_uid: $org_uid, name: $name})
        ON CREATE SET t.uid = randomUUID(), t.created = timestamp()
        MERGE (t)-[:IN_ORG]->(o)
        RETURN t.uid AS uid, t.name AS name, t.org_uid AS org_uid
        """,
        org_uid=org_uid,
        name=name,
    ).single()
    return dict(record) if record else None


def create_account(
    session: Session, org_uid: str, name: str, team_uid: str | None, role: str
) -> dict | None:
    record = session.run(
        """
        MATCH (o:Org {uid: $org_uid})
        OPTIONAL MATCH (tm:Team {uid: $team_uid, org_uid: $org_uid})
        WITH o, tm
        WHERE $team_uid IS NULL OR tm IS NOT NULL
        MERGE (a:Account {org_uid: $org_uid, name: $name})
        ON CREATE SET a.uid = randomUUID(), a.created = timestamp()
        SET a.role = $role, a.team_uid = CASE WHEN tm IS NULL THEN NULL ELSE tm.uid END
        MERGE (a)-[:IN_ORG]->(o)
        FOREACH (_ IN CASE WHEN tm IS NULL THEN [] ELSE [1] END | MERGE (a)-[:IN_TEAM]->(tm))
        RETURN a.uid AS uid, a.name AS name, a.org_uid AS org_uid,
               a.team_uid AS team_uid, a.role AS role
        """,
        org_uid=org_uid,
        team_uid=team_uid,
        name=name,
        role=role,
    ).single()
    return dict(record) if record else None


def create_token(
    session: Session, account_uid: str, label: str | None, expires_days: int | None
) -> dict | None:
    """Create an account token; the plaintext is returned once and only its hash stored."""
    plaintext = pysecrets.token_urlsafe(32)
    record = session.run(
        """
        MATCH (a:Account {uid: $account_uid})
        CREATE (t:Token {hash: $hash, label: $label, revoked: false,
                         created: timestamp(),
                         expires_at: CASE WHEN $expires_days IS NULL THEN NULL
                                     ELSE timestamp() + $expires_days * 86400000 END})
        CREATE (a)-[:HAS_TOKEN]->(t)
        RETURN t.hash AS hash
        """,
        account_uid=account_uid,
        hash=hash_token(plaintext),
        label=label,
        expires_days=expires_days,
    ).single()
    if record is None:
        return None
    return {"token": plaintext, "label": label}


def revoke_token(session: Session, token_hash: str) -> bool:
    record = session.run(
        "MATCH (t:Token {hash: $hash}) SET t.revoked = true RETURN t.hash AS hash",
        hash=token_hash,
    ).single()
    return record is not None
