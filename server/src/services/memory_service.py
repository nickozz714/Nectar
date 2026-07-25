from __future__ import annotations

import re

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.config import get_settings
from src.repository import audit_repo, graph_repo
from src.services.embeddings import embed

# Deterministic write-gate: the server holds no judgement, only hard checks.
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("phone", re.compile(r"(\+31|0031|\b06)[\s-]?\d{8,9}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("bsn-like", re.compile(r"\b\d{9}\b")),
]


def detect_pii(text: str) -> list[str]:
    return [kind for kind, pattern in _PII_PATTERNS if pattern.search(text)]


def remember(
    session: Session,
    account: AuthedAccount,
    type_: str,
    title: str,
    content: str,
    parent_topics: list[str],
    scope: str = "team",
) -> dict:
    """Direct write through the write-gate: PII filter + embedding dedup.
    Default scope is team (org when the account has no team). Topics are org-scoped
    structure and are found-or-created."""
    settings = get_settings()
    notes: list[str] = []

    if type_ not in graph_repo.KNOWLEDGE_TYPES or type_ == "topic":
        raise ValueError(
            f"type must be one of: {', '.join(t for t in graph_repo.KNOWLEDGE_TYPES if t != 'topic')}"
        )
    if scope not in ("org", "team", "account"):
        raise ValueError("scope must be org, team or account")
    if scope == "team" and account.team_uid is None:
        scope = "org"
        notes.append("account has no team; scope fell back to org")

    pii = detect_pii(f"{title}\n{content}")
    if pii:
        raise ValueError(
            f"Rejected by the PII filter ({', '.join(pii)}). "
            "Rephrase without personal data and try again."
        )

    embedding = embed(f"{title}\n{content}")
    if embedding is not None:
        nearest = graph_repo.vector_candidates(session, account, embedding, k=1, allowed=None)
        if nearest and nearest[0][1] >= settings.DEDUP_SIMILARITY_THRESHOLD:
            existing, sim = nearest[0]
            graph_repo.touch_nodes(session, [existing["uid"]])
            return {
                "created": False,
                "existing_uid": existing["uid"],
                "existing_title": existing["title"],
                "note": f"Near-duplicate (similarity {sim:.2f}) of an existing node; "
                "it was touched instead. Use hive_suggest to propose an edit if it is outdated.",
            }

    node = graph_repo.create_knowledge(session, account, type_, title, content, scope, embedding)

    linked = []
    for topic_title in parent_topics or []:
        topic = graph_repo.find_or_create_topic(session, account.org_uid, topic_title, account.uid)
        graph_repo.link(session, account, topic["uid"], node["uid"], "contains")
        linked.append(topic["title"])
        if topic["created"]:
            notes.append(f"new topic created: {topic['title']}")
    if not linked:
        notes.append("no parent topics given — link it later with hive_relate")

    audit_repo.log(
        session, account.org_uid, account.uid, "remember", node["uid"],
        {"type": type_, "title": title, "scope": scope, "topics": linked},
    )
    return {"created": True, "uid": node["uid"], "topics": linked, "notes": notes}
