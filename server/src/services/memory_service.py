from __future__ import annotations

import re

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.components.config import get_settings
from src.repository import audit_repo, governance_repo, graph_repo, tenancy_repo
from src.components.embeddings import embed

# Deterministic write-gate: the server holds no judgement, only hard checks.


_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("phone", re.compile(r"(\+31|0031|\b06)[\s-]?\d{8,9}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("bsn-like", re.compile(r"\b\d{9}\b")),
]


def detect_pii(text: str) -> list[str]:
    return [kind for kind, pattern in _PII_PATTERNS if pattern.search(text)]


# Purview-style sensitivity classification — deterministic and transparent. PII is
# hard-blocked; credential-shaped content is allowed but labeled 'gevoelig' so the
# governance dashboard surfaces it for review.
# Sensitivity flags an actual secret VALUE, not a technical discussion that merely mentions
# auth. So a memory about "reading the Authorization header / bearer-auth" is NOT sensitive;
# a real token, key or `password = ...` assignment is.
_SENSITIVE_PATTERNS = [
    # a secret keyword actually assigned a value (password: hunter2, api_key = abc123…)
    re.compile(r"(?i)\b(wachtwoord|password|passphrase|api[-_ ]?key|client[-_ ]?secret|secret|"
               r"credential|private[-_ ]?key|\bPAT)\b\s*[:=]\s*['\"]?\S{6,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),          # a real bearer token value
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
               r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),      # common concrete token formats
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),    # JWT (two segments)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def classify_sensitivity(text: str) -> str:
    return "gevoelig" if any(p.search(text) for p in _SENSITIVE_PATTERNS) else "intern"


def assert_no_pii(text: str) -> None:
    pii = detect_pii(text)
    if pii:
        raise ValueError(
            f"Rejected by the PII filter ({', '.join(pii)}). "
            "Rephrase without personal data and try again."
        )


def link_topics(
    session: Session, account: AuthedAccount, node_uid: str, parent_topics: list[str]
) -> tuple[list[str], list[str]]:
    """Link a node under parent topics. Exact matches merge; semantically similar
    existing topics are reused instead of creating near-duplicates; only then is a
    new topic created."""
    settings = get_settings()
    linked: list[str] = []
    notes: list[str] = []
    for title in parent_topics or []:
        title = title.strip()
        if not title:
            continue
        title_embedding = embed(title)
        topic_uid = None
        if title_embedding is not None:
            similar = graph_repo.find_similar_topic(
                session, account, title_embedding, settings.TOPIC_SIMILARITY_THRESHOLD
            )
            if similar is not None and similar["title"].lower() != title.lower():
                topic_uid = similar["uid"]
                notes.append(
                    f"linked under existing topic '{similar['title']}' instead of creating "
                    f"near-duplicate topic '{title}'"
                )
                linked.append(similar["title"])
        if topic_uid is None:
            topic = graph_repo.find_or_create_topic(
                session, account.org_uid, title, account.uid, embedding=title_embedding
            )
            topic_uid = topic["uid"]
            linked.append(topic["title"])
            if topic["created"]:
                notes.append(f"new topic created: {topic['title']}")
        graph_repo.link(session, account, topic_uid, node_uid, "contains")
    return linked, notes


def remember(
    session: Session,
    account: AuthedAccount,
    type_: str,
    title: str,
    content: str,
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
    force: bool = False,
    tags: list[str] | None = None,
    parent_node: str = "",
) -> dict:
    """Direct write through the write-gate: quality checks + PII filter + dedup.
    Hard duplicates are rejected; grey-zone lookalikes are created but flagged as a
    dedup chore for the swarm. `force=True` skips the dedup check entirely — for a
    genuine false positive that must be created anyway. Quality + PII always apply.
    Default scope is team (org when the account has no team)."""
    settings = get_settings()
    notes: list[str] = []
    title = title.strip()
    content = content.strip()

    if type_ not in graph_repo.KNOWLEDGE_TYPES or type_ == "topic":
        raise ValueError(
            f"type must be one of: {', '.join(t for t in graph_repo.KNOWLEDGE_TYPES if t != 'topic')}"
        )
    if scope not in ("org", "team", "account"):
        raise ValueError("scope must be org, team or account")
    if scope == "team" and account.team_uid is None:
        scope = "org"
        notes.append("account has no team; scope fell back to org")
    if len(title) < settings.MIN_TITLE_LENGTH:
        raise ValueError(
            "Title too short — make it specific and searchable "
            "(e.g. 'Fabric Data Agents require OBO auth', not 'Fabric issue')."
        )
    if len(content) < settings.MIN_CONTENT_LENGTH:
        raise ValueError(
            "Content too short — a memory must be self-contained so a colleague's model "
            "can apply it cold. Add the what, the why and the how."
        )
    assert_no_pii(f"{title}\n{content}")

    embedding = embed(f"{title}\n{content}")
    grey_zone_of: dict | None = None
    if embedding is not None and not force:
        nearest = graph_repo.vector_candidates(session, account, embedding, k=1, allowed=None)
        if nearest:
            existing, sim = nearest[0]
            if sim >= settings.DEDUP_SIMILARITY_THRESHOLD:
                graph_repo.touch_nodes(session, [existing["uid"]])
                return {
                    "created": False,
                    "existing_uid": existing["uid"],
                    "existing_title": existing["title"],
                    "note": f"Near-duplicate (similarity {sim:.2f}) of an existing node; it was "
                    "touched instead. Re-run with force=True if this is a genuine false positive, "
                    "or use hive_suggest to propose an edit if the existing one is outdated.",
                }
            if sim >= settings.DEDUP_REVIEW_THRESHOLD and existing.get("type") != "topic":
                if existing.get("type") == type_:
                    grey_zone_of = {"uid": existing["uid"], "title": existing["title"], "sim": sim}
                else:
                    # Cross-type lookalikes (a learning next to the decision it came from, a
                    # process next to its pitfall) are how the hive is MEANT to grow — flagging
                    # them buries the swarm in "keep both" verdicts, so only same-type pairs
                    # become an op_route Pollen.
                    notes.append(
                        f"similar to existing '{existing['title']}' ({existing.get('type')}, "
                        f"similarity {sim:.2f}) but of a different type; kept both without a "
                        "review-Pollen — consider hive_relate to link them"
                    )

    node = graph_repo.create_knowledge(
        session, account, type_, title, content, scope, embedding, created_by_model=model_name,
        sensitivity=classify_sensitivity(f"{title}\n{content}"),
    )

    if grey_zone_of is not None:
        # op_route think-Pollen: instead of a silent dedup vote, pose a REASONING task to the
        # swarm — a visiting agent decides ADD / UPDATE / DELETE / NOOP given both memories.
        governance_repo.create_think_pollen(
            session, account, node["uid"], "op_route",
            {
                "instruction": ("Twee bijna-gelijke memories. Beslis: ADD (het zijn echt aparte "
                                "weetjes, behoud beide), UPDATE (voeg samen tot één betere — lever "
                                "merged_title + merged_content), DELETE (dit nieuwe is een dubbel, "
                                "schrap het), of NOOP (laat zo). ADD/NOOP mag elk Swarm-lid; alleen "
                                "voor UPDATE/DELETE/REPLACE geldt: niet door de schrijver van de "
                                "nieuwe memory zelf, tenzij die org_admin is (een admin mag altijd)."),
                "duplicate_uid": grey_zone_of["uid"],
                "duplicate_title": grey_zone_of["title"],
                "similarity": round(grey_zone_of["sim"], 3),
                "decisions": ["ADD", "UPDATE", "DELETE", "NOOP"],
            },
            idem_key=f"op_route:{node['uid']}",
        )
        notes.append(
            f"similar to existing '{grey_zone_of['title']}' (similarity {grey_zone_of['sim']:.2f}); "
            "an op-route think-Pollen was filed for the swarm to reconcile"
        )

    if force:
        notes.append("created with force — dedup check skipped")
    if tags:
        graph_repo.set_tags(session, account.org_uid, node["uid"], tags)
    linked, topic_notes = link_topics(session, account, node["uid"], parent_topics)
    notes.extend(topic_notes)
    # Optionally hang this node under a specific parent node (e.g. a learning under the
    # memory/skill/workflow it came from), as a CONTAINS child.
    if parent_node.strip():
        try:
            graph_repo.link(session, account, parent_node.strip(), node["uid"], "contains")
            notes.append(f"linked as a child of node {parent_node.strip()}")
        except ValueError as exc:
            notes.append(f"could not link under parent node: {exc}")
    if not linked and not parent_node.strip():
        notes.append("no parent topics given — link it later with hive_relate")

    audit_repo.log(
        session, account.org_uid, account.uid, "remember", node["uid"],
        {"type": type_, "title": title, "scope": scope, "topics": linked, "model": model_name},
    )
    return {"created": True, "uid": node["uid"], "topics": linked, "notes": notes}
