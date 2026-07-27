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
    session: Session, org_uid: str, name: str, team_uid: str | None, role: str,
    person: str | None = None, email: str | None = None,
) -> dict | None:
    """An account always belongs to a PERSON (the human accountable for it) — also when
    the account is used by a model: tokens -> account -> person is the lineage chain."""
    record = session.run(
        """
        MATCH (o:Org {uid: $org_uid})
        OPTIONAL MATCH (tm:Team {uid: $team_uid, org_uid: $org_uid})
        WITH o, tm
        WHERE $team_uid IS NULL OR tm IS NOT NULL
        MERGE (a:Account {org_uid: $org_uid, name: $name})
        ON CREATE SET a.uid = randomUUID(), a.created = timestamp()
        SET a.role = $role, a.team_uid = CASE WHEN tm IS NULL THEN NULL ELSE tm.uid END,
            a.person = coalesce($person, a.person), a.email = coalesce($email, a.email)
        MERGE (a)-[:IN_ORG]->(o)
        FOREACH (_ IN CASE WHEN tm IS NULL THEN [] ELSE [1] END | MERGE (a)-[:IN_TEAM]->(tm))
        RETURN a.uid AS uid, a.name AS name, a.org_uid AS org_uid,
               a.team_uid AS team_uid, a.role AS role, a.person AS person, a.email AS email
        """,
        org_uid=org_uid,
        team_uid=team_uid,
        name=name,
        role=role,
        person=person,
        email=email,
    ).single()
    return dict(record) if record else None


def create_token(
    session: Session, account_uid: str, label: str | None, expires_days: int | None,
    role: str | None = None,
) -> dict | None:
    """Create an account token; the plaintext is returned once and only its hash stored.
    The role is bound to the TOKEN (falls back to the account role when null)."""
    plaintext = pysecrets.token_urlsafe(32)
    record = session.run(
        """
        MATCH (a:Account {uid: $account_uid})
        CREATE (t:Token {hash: $hash, label: $label, revoked: false, role: $role,
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
        role=role,
    ).single()
    if record is None:
        return None
    return {"token": plaintext, "label": label, "role": role}


def set_token_role(session: Session, token_hash: str, role: str) -> bool:
    record = session.run(
        "MATCH (t:Token {hash: $hash}) SET t.role = $role RETURN t.hash AS hash",
        hash=token_hash,
        role=role,
    ).single()
    return record is not None


def set_password(session: Session, account_uid: str, password_hash: str) -> bool:
    record = session.run(
        "MATCH (a:Account {uid: $uid}) SET a.password_hash = $h RETURN a.uid AS uid",
        uid=account_uid,
        h=password_hash,
    ).single()
    return record is not None


def set_password_by_name(session: Session, org_uid: str, name: str, password_hash: str) -> bool:
    record = session.run(
        "MATCH (a:Account {org_uid: $org_uid, name: $name}) SET a.password_hash = $h "
        "RETURN a.uid AS uid",
        org_uid=org_uid,
        name=name,
        h=password_hash,
    ).single()
    return record is not None


def get_account_for_login(session: Session, name: str) -> dict | None:
    """Look up an account by username for password login. Returns the password hash too.
    Names are unique per org; on a single-org deployment the name is unambiguous."""
    record = session.run(
        """
        MATCH (a:Account {name: $name})
        RETURN a.uid AS uid, a.org_uid AS org_uid, a.name AS name, a.role AS role,
               a.password_hash AS password_hash
        ORDER BY a.created LIMIT 1
        """,
        name=name,
    ).single()
    return dict(record) if record else None


def set_account_role(session: Session, org_uid: str, account_name: str, role: str) -> bool:
    """Promote/demote a person: set the role on their account AND all its tokens (role is
    token-bound, so both must move)."""
    record = session.run(
        """
        MATCH (a:Account {org_uid: $org_uid, name: $name})
        SET a.role = $role
        WITH a
        OPTIONAL MATCH (a)-[:HAS_TOKEN]->(t:Token)
        SET t.role = $role
        RETURN a.uid AS uid
        """,
        org_uid=org_uid,
        name=account_name,
        role=role,
    ).single()
    return record is not None


def revoke_token(session: Session, token_hash: str) -> bool:
    record = session.run(
        "MATCH (t:Token {hash: $hash}) SET t.revoked = true RETURN t.hash AS hash",
        hash=token_hash,
    ).single()
    return record is not None


def list_accounts(session: Session, org_uid: str) -> list[dict]:
    result = session.run(
        """
        MATCH (a:Account {org_uid: $org_uid})
        OPTIONAL MATCH (a)-[:HAS_TOKEN]->(t:Token)
        WITH a, count(t) AS tokens,
             sum(CASE WHEN t.revoked = false AND
                 (t.expires_at IS NULL OR t.expires_at > timestamp()) THEN 1 ELSE 0 END) AS active
        RETURN a.uid AS uid, a.name AS name, a.person AS person, a.role AS role,
               a.team_uid AS team_uid, tokens, active
        ORDER BY a.name
        """,
        org_uid=org_uid,
    )
    return [dict(r) for r in result]


def list_tokens(session: Session, account_uid: str) -> list[dict]:
    """Token metadata only — the plaintext is never stored, so it can't be listed."""
    result = session.run(
        """
        MATCH (:Account {uid: $account_uid})-[:HAS_TOKEN]->(t:Token)
        RETURN t.hash AS hash, t.label AS label, t.revoked AS revoked,
               t.created AS created, t.expires_at AS expires_at, t.last_used AS last_used,
               (t.revoked = false AND (t.expires_at IS NULL OR t.expires_at > timestamp())) AS active
        ORDER BY t.created DESC
        """,
        account_uid=account_uid,
    )
    return [dict(r) for r in result]


def rotate_token(
    session: Session, token_hash: str, expires_days: int | None
) -> dict | None:
    """Revoke an existing token and mint a fresh one for the same account + label."""
    account = session.run(
        """
        MATCH (a:Account)-[:HAS_TOKEN]->(t:Token {hash: $hash})
        SET t.revoked = true
        RETURN a.uid AS uid, t.label AS label
        """,
        hash=token_hash,
    ).single()
    if account is None:
        return None
    return create_token(session, account["uid"], account["label"], expires_days)


def cleanup_tokens(session: Session, org_uid: str) -> int:
    """Delete revoked and expired tokens org-wide. Returns how many were removed."""
    record = session.run(
        """
        MATCH (a:Account {org_uid: $org_uid})-[:HAS_TOKEN]->(t:Token)
        WHERE t.revoked = true OR (t.expires_at IS NOT NULL AND t.expires_at <= timestamp())
        WITH t, count(t) AS _
        DETACH DELETE t
        RETURN count(*) AS removed
        """,
        org_uid=org_uid,
    ).single()
    return record["removed"] if record else 0


def list_orgs(session: Session) -> list[dict]:
    result = session.run(
        """
        MATCH (o:Org)
        OPTIONAL MATCH (a:Account {org_uid: o.uid})
        OPTIONAL MATCH (n:Knowledge {org_uid: o.uid})
        RETURN o.uid AS uid, o.name AS name,
               count(DISTINCT a) AS accounts, count(DISTINCT n) AS nodes
        ORDER BY o.name
        """
    )
    return [dict(r) for r in result]
