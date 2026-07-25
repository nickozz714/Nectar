from __future__ import annotations

from contextlib import contextmanager

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from src.authentication.deps import AuthedAccount, account_from_token
from src.db.neo4j import graph_session
from src.repository import governance_repo, graph_repo
from src.services import governance_service, memory_service, search_service

mcp = FastMCP(
    "HiveMind",
    instructions=(
        "The shared mind of your organization. Consult it before starting work, write "
        "back reusable knowledge, and — when a chore is ready — help maintain the hive."
    ),
)


@contextmanager
def _authed():
    headers = get_http_headers()
    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ValueError("Missing Bearer token (HIVE_TOKEN)")
    with graph_session() as session:
        account: AuthedAccount = account_from_token(session, auth[7:].strip())
        yield session, account


@mcp.tool
def hive_search(query: str, anchors: list[str] | None = None, limit: int = 8) -> str:
    """Search the hive's shared memory. Results are ranked by semantic relevance and
    freshness (recently-used knowledge first). Pass `anchors` (topic titles, e.g. your
    project's topics) to search that slice of the mind first. Reading a memory
    rejuvenates it."""
    with _authed() as (session, account):
        results = search_service.search(session, account, query, anchors=anchors, limit=limit)
        text = search_service.render_results(results)
        ready = governance_repo.ready_count(session, account)
        if ready:
            text += f"\n\n⚙ {ready} hive chore(s) ready — call hive_chores() when convenient."
        return text


@mcp.tool
def hive_get(node_uid: str) -> dict:
    """Fetch one knowledge node in full, including its parent topics, children and
    related nodes. Use after hive_search to read the complete content."""
    with _authed() as (session, account):
        node = graph_repo.get_node(session, account, node_uid)
        if node is None:
            raise ValueError("Node not found or not visible to this account")
        graph_repo.touch_nodes(session, [node_uid])
        return node


@mcp.tool
def hive_remember(
    type: str,
    title: str,
    content: str,
    parent_topics: list[str],
    scope: str = "team",
) -> dict:
    """Write reusable knowledge into the hive. type: memory | process | skill |
    convention | decision | glossary. Link it under parent topics (subjects, projects or
    systems — e.g. 'Data Modelling', 'Swinkels'); missing topics are created. scope:
    team (default), org, or account. Personal data (PII) is rejected; near-duplicates
    are deduplicated automatically. Only store knowledge that is reusable for the
    organization — no session noise."""
    with _authed() as (session, account):
        return memory_service.remember(
            session, account, type, title, content, parent_topics, scope
        )


@mcp.tool
def hive_relate(parent_uid: str, child_uid: str, relation: str = "contains") -> dict:
    """Link two knowledge nodes: 'contains' (hierarchy, topic -> knowledge) or 'relates'
    (free association). A node may sit under multiple parents — that is how knowledge
    transfers across contexts."""
    with _authed() as (session, account):
        if not graph_repo.link(session, account, parent_uid, child_uid, relation):
            raise ValueError("One of the nodes was not found in your org")
        return {"linked": True, "relation": relation}


@mcp.tool
def hive_suggest(
    kind: str, node_uid: str, payload: dict, rationale: str, model_name: str = ""
) -> dict:
    """Propose a mutation of an existing memory — memories are not casually editable.
    kind: edit (payload: {title?, content?}), invalidate, dedup_merge (payload:
    {duplicate_uid}), promotion (payload: {target_topic} — for knowledge that proved
    generic beyond its origin context), scope_widening (payload: {target_scope} — always
    reviewed by a human). Identical suggestions from multiple models accumulate votes;
    at the consensus threshold the chore becomes ready for the swarm."""
    with _authed() as (session, account):
        return governance_service.suggest(
            session, account, kind, node_uid, payload, rationale, model_name
        )


@mcp.tool
def hive_chores(limit: int = 5) -> list[dict]:
    """List pending governance chores (ready first). The hive has no central maintainer:
    a bee that is reading or writing anyway picks up a ready chore and resolves it with
    hive_resolve_chore."""
    with _authed() as (session, account):
        return governance_repo.open_chores(session, account, limit)


@mcp.tool
def hive_resolve_chore(chore_uid: str, action: str, note: str = "") -> dict:
    """Resolve a 'ready' chore: action 'apply' executes the suggested mutation, 'reject'
    dismisses it. Judge the suggestion on its merits first — you are the reviewing bee.
    scope_widening chores are excluded (human review only)."""
    with _authed() as (session, account):
        return governance_service.resolve(session, account, chore_uid, action, note)


@mcp.tool
def topic_list() -> list[dict]:
    """List the visible topic nodes (the top of the mind) with their child counts. Use
    to orient, to pick anchors, or to decide where new knowledge belongs."""
    with _authed() as (session, account):
        return graph_repo.list_topics(session, account)


@mcp.tool
def skill_list() -> str:
    """List shared skills available in the hive."""
    with _authed() as (session, account):
        skills = graph_repo.list_skills(session, account)
        if not skills:
            return "No skills in the hive yet."
        return "\n".join(f"- **{n['title']}** (uid: {n['uid']})" for n in skills)


@mcp.tool
def skill_get(skill_uid: str) -> dict:
    """Fetch a shared skill: its description plus attached files (SKILL.md and
    resources) in the Claude Code skill format."""
    with _authed() as (session, account):
        node = graph_repo.get_node(session, account, skill_uid)
        if node is None or node.get("type") != "skill":
            raise ValueError("Skill not found or not visible")
        node["files"] = graph_repo.skill_files(session, account, skill_uid)
        return node
