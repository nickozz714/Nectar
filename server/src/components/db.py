from __future__ import annotations

import time
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase

from src.components.config import get_settings

_driver: Driver | None = None

CONSTRAINTS = [
    "CREATE CONSTRAINT org_name IF NOT EXISTS FOR (o:Org) REQUIRE o.name IS UNIQUE",
    "CREATE CONSTRAINT org_uid IF NOT EXISTS FOR (o:Org) REQUIRE o.uid IS UNIQUE",
    "CREATE CONSTRAINT account_uid IF NOT EXISTS FOR (a:Account) REQUIRE a.uid IS UNIQUE",
    "CREATE CONSTRAINT team_uid IF NOT EXISTS FOR (t:Team) REQUIRE t.uid IS UNIQUE",
    "CREATE CONSTRAINT token_hash IF NOT EXISTS FOR (t:Token) REQUIRE t.hash IS UNIQUE",
    "CREATE CONSTRAINT knowledge_uid IF NOT EXISTS FOR (n:Knowledge) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT pollen_uid IF NOT EXISTS FOR (c:Pollen) REQUIRE c.uid IS UNIQUE",
    "CREATE CONSTRAINT secret_uid IF NOT EXISTS FOR (s:Secret) REQUIRE s.uid IS UNIQUE",
    "CREATE CONSTRAINT invite_hash IF NOT EXISTS FOR (i:Invite) REQUIRE i.code_hash IS UNIQUE",
]

# Idempotent data migrations run on every startup (no-ops once applied).
MIGRATIONS = [
    # Rebrand: the governance task node is now :Pollen (was :Chore). Relabel any legacy nodes.
    "MATCH (c:Chore) SET c:Pollen REMOVE c:Chore",
    # Bloom backfill: give legacy nodes (created before the lifecycle field) an HONEST state so
    # the badge/recall aren't misleading. Only touches nodes with no lifecycle yet, so newly
    # 'captured' writes are never overwritten. Established/durable knowledge → mature, archived
    # or superseded → deprecated, the rest → validated.
    """
    MATCH (n:Knowledge) WHERE n.type <> 'topic' AND n.lifecycle IS NULL
    SET n.lifecycle = CASE
        WHEN coalesce(n.archived, false) = true OR n.superseded_by IS NOT NULL THEN 'deprecated'
        WHEN n.type IN ['convention', 'decision', 'learning'] OR coalesce(n.use_count, 0) >= 3 THEN 'mature'
        ELSE 'validated' END
    """,
]


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _driver


@contextmanager
def graph_session():
    with get_driver().session() as session:
        yield session


def get_graph():
    """FastAPI dependency."""
    with graph_session() as session:
        yield session


def init_db(retries: int = 90, delay: float = 2.0) -> None:
    """Wait for Neo4j, then ensure constraints and the vector index exist."""
    settings = get_settings()
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            get_driver().verify_connectivity()
            last_err = None
            break
        except Exception as exc:  # neo4j may still be booting
            last_err = exc
            time.sleep(delay)
    if last_err is not None:
        raise last_err

    with graph_session() as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)
        for stmt in MIGRATIONS:
            session.run(stmt)
        # Full-text (Lucene/BM25) index for hybrid retrieval — catches exact tokens
        # (symbol names, error codes, paths) that embeddings blur. Always created.
        session.run(
            "CREATE FULLTEXT INDEX knowledge_fulltext IF NOT EXISTS "
            "FOR (n:Knowledge) ON EACH [n.title, n.content]"
        )
        if settings.embeddings_enabled:
            session.run(
                "CREATE VECTOR INDEX knowledge_embedding IF NOT EXISTS "
                "FOR (n:Knowledge) ON (n.embedding) "
                "OPTIONS {indexConfig: {`vector.dimensions`: $dim, "
                "`vector.similarity_function`: 'cosine'}}",
                dim=settings.EMBEDDINGS_DIM,
            )


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
