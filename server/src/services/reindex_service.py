from __future__ import annotations

from neo4j import Session

from src.components.config import get_settings
from src.components.embeddings import embed


def reembed(session: Session, org_uid: str | None = None, batch: int = 100) -> dict:
    """Recompute embeddings for every knowledge node (skips topics, whose title-only
    embedding is set on creation). Needed after switching embedding model or turning
    embeddings on for an existing corpus. Idempotent; safe to re-run."""
    if not get_settings().embeddings_enabled:
        return {"reembedded": 0, "skipped": 0, "note": "embeddings disabled"}

    rows = session.run(
        """
        MATCH (n:Knowledge)
        WHERE ($org_uid IS NULL OR n.org_uid = $org_uid) AND n.type <> 'topic'
        RETURN n.uid AS uid, n.title AS title, n.content AS content
        """,
        org_uid=org_uid,
    ).data()

    done, failed = 0, 0
    pending: list[dict] = []
    for r in rows:
        vec = embed(f"{r['title']}\n{r.get('content') or ''}")
        if vec is None:
            failed += 1
            continue
        pending.append({"uid": r["uid"], "vec": vec})
        if len(pending) >= batch:
            _flush(session, pending)
            done += len(pending)
            pending = []
    if pending:
        _flush(session, pending)
        done += len(pending)
    return {"reembedded": done, "failed": failed, "total": len(rows)}


def _flush(session: Session, pending: list[dict]) -> None:
    session.run(
        """
        UNWIND $rows AS row
        MATCH (n:Knowledge {uid: row.uid})
        SET n.embedding = row.vec
        """,
        rows=pending,
    )
