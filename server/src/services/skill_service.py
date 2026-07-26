from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.repository import audit_repo, graph_repo
from src.services.embeddings import embed
from src.services.memory_service import assert_no_pii, classify_sensitivity, link_topics


def put_artifact(
    session: Session,
    account: AuthedAccount,
    type_: str,
    title: str,
    description: str,
    files: list[dict],
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
    required_file: str | None = None,
) -> dict:
    """Create or update a file-backed knowledge unit (skill or workflow). The creator
    may update their own directly; anyone else must go through hive_suggest —
    mutations stay consensus-gated."""
    title = title.strip()
    if not title:
        raise ValueError(f"A {type_} needs a title")
    if scope not in ("org", "team", "account"):
        raise ValueError("scope must be org, team or account")
    if scope == "team" and account.team_uid is None:
        scope = "org"
    if not files or not all(f.get("path") and f.get("content") for f in files):
        raise ValueError("files must be a non-empty list of {path, content}")
    if required_file and not any(f["path"] == required_file for f in files):
        raise ValueError(f"A {type_} must contain a {required_file} file")
    assert_no_pii(description + "\n" + "\n".join(f["content"] for f in files))

    embedding = embed(f"{title}\n{description}")
    existing = graph_repo.get_artifact_by_title(session, account, type_, title)
    notes: list[str] = []

    if existing is not None:
        if existing["created_by"] != account.uid:
            raise ValueError(
                f"{type_.capitalize()} '{existing['title']}' exists and belongs to another "
                "account. Propose changes with hive_suggest(kind='edit', ...) instead."
            )
        graph_repo.update_node(session, existing["uid"], {"content": description}, embedding)
        graph_repo.replace_skill_files(session, existing["uid"], files)
        graph_repo.touch_nodes(session, [existing["uid"]])
        audit_repo.log(session, account.org_uid, account.uid, f"{type_}_update", existing["uid"],
                       {"title": title, "files": [f["path"] for f in files]})
        return {"created": False, "updated": True, "uid": existing["uid"], "notes": notes}

    node = graph_repo.create_knowledge(
        session, account, type_, title, description, scope, embedding,
        created_by_model=model_name,
        sensitivity=classify_sensitivity(
            description + "\n" + "\n".join(f["content"] for f in files)
        ),
    )
    graph_repo.replace_skill_files(session, node["uid"], files)
    linked, topic_notes = link_topics(session, account, node["uid"], parent_topics)
    notes.extend(topic_notes)
    audit_repo.log(session, account.org_uid, account.uid, f"{type_}_create", node["uid"],
                   {"title": title, "scope": scope, "files": [f["path"] for f in files]})
    return {"created": True, "uid": node["uid"], "topics": linked, "notes": notes}


def put_skill(
    session: Session,
    account: AuthedAccount,
    title: str,
    description: str,
    files: list[dict],
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
) -> dict:
    return put_artifact(
        session, account, "skill", title, description, files, parent_topics, scope,
        model_name, required_file="SKILL.md",
    )


def put_workflow(
    session: Session,
    account: AuthedAccount,
    title: str,
    description: str,
    files: list[dict],
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
) -> dict:
    return put_artifact(
        session, account, "workflow", title, description, files, parent_topics, scope,
        model_name, required_file=None,
    )
