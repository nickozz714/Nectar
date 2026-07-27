from __future__ import annotations

from contextlib import contextmanager

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from src.authentication.deps import AuthedAccount, account_from_token
from src.db.neo4j import graph_session
from src.repository import governance_repo, graph_repo, session_repo
from src.services import (
    governance_service,
    kit_service,
    memory_service,
    org_service,
    search_service,
    skill_service,
)

mcp = FastMCP(
    "HiveMind",
    instructions=(
        "The shared mind of your organization. Consult it before starting work, write "
        "back reusable knowledge, and — when a chore is ready — help maintain the hive."
    ),
)


@contextmanager
def _authed():
    request = get_http_request()
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ValueError("Missing Bearer token (HIVE_TOKEN)")
    with graph_session() as session:
        account: AuthedAccount = account_from_token(session, auth[7:].strip())
        yield session, account


@mcp.tool
def hive_search(query: str, anchors: list[str] | None = None, limit: int = 8) -> str:
    """Search the hive's shared memory. Results are ranked by semantic relevance and
    freshness (recently-used knowledge first). Pass `anchors` (topic titles, e.g. your
    project's topics from HIVE_ANCHORS) to boost that slice of the mind in the ranking —
    a preference, not a filter: knowledge from other contexts stays findable and may
    still be the answer. Reading a memory rejuvenates it."""
    with _authed() as (session, account):
        results = search_service.search(session, account, query, anchors=anchors, limit=limit)
        text = search_service.render_results(results)
        ready = governance_repo.ready_count(session, account)
        if ready:
            text += f"\n\n⚙ {ready} hive chore(s) ready — call hive_chores() when convenient."
        return text


@mcp.tool
def hive_get(node_uid: str) -> dict:
    """Fetch one knowledge node in full, including its parent topics, children, related
    nodes and attached files (skills/workflows). Use after hive_search to read the
    complete content."""
    with _authed() as (session, account):
        node = graph_repo.get_node(session, account, node_uid)
        if node is None:
            raise ValueError("Node not found or not visible to this account")
        files = graph_repo.node_files(session, account, node_uid)
        if files:
            node["files"] = files
        graph_repo.touch_nodes(session, [node_uid])
        return node


@mcp.tool
def hive_remember(
    type: str,
    title: str,
    content: str,
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
    force: bool = False,
) -> dict:
    """Write reusable knowledge into the hive. type: memory | process | workflow |
    convention | decision | glossary (for file-backed skills/workflows use skill_put /
    workflow_put). Set force=True to create anyway when a previous call was rejected as a
    near-duplicate but it is genuinely new (a dedup false positive). Link it under parent topics
    (subjects, projects or systems — e.g. 'Data Modelling', 'Swinkels'); semantically
    similar existing topics are reused, only then is a new topic created. scope: team
    (default), org, or account. The write-gate enforces: specific title, self-contained
    content, no personal data (PII), and dedup — hard duplicates are rejected, close
    lookalikes are created but flagged as a dedup chore for the swarm. Pass model_name
    (your model id) for provenance. Only store knowledge that is reusable for the
    organization — no session noise."""
    with _authed() as (session, account):
        return memory_service.remember(
            session, account, type, title, content, parent_topics, scope, model_name, force
        )


@mcp.tool
def skill_put(
    title: str,
    description: str,
    files: list[dict],
    parent_topics: list[str] | None = None,
    scope: str = "team",
    model_name: str = "",
) -> dict:
    """Publish or update a shared skill in the hive, in the Claude Code skill format:
    files must be a list of {path, content} and include a SKILL.md. The creator may
    update their own skill directly; someone else's skill is changed via hive_suggest
    (mutations stay consensus-gated). The PII filter applies to all file contents."""
    with _authed() as (session, account):
        return skill_service.put_skill(
            session, account, title, description, files, parent_topics or [], scope, model_name
        )


@mcp.tool
def workflow_put(
    title: str,
    description: str,
    files: list[dict],
    parent_topics: list[str] | None = None,
    scope: str = "team",
    model_name: str = "",
) -> dict:
    """Publish or update a shared workflow: a step-by-step or executable working
    procedure, with files ({path, content} — e.g. workflow.md or a script). Workflows
    can stand alone under a topic or be linked under a skill with hive_relate. The
    creator may update their own workflow directly; someone else's goes through
    hive_suggest. For a purely textual workflow without files, hive_remember with
    type='workflow' also works."""
    with _authed() as (session, account):
        return skill_service.put_workflow(
            session, account, title, description, files, parent_topics or [], scope, model_name
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
    dismisses it. Requires the maintainer role on your account — members can suggest and
    vote, but resolving is delegated deliberately. Judge the suggestion on its merits
    first — you are the reviewing bee. scope_widening chores are excluded (human review
    only)."""
    with _authed() as (session, account):
        return governance_service.resolve(session, account, chore_uid, action, note)


@mcp.tool
def hive_invite(role: str = "member", uses: int = 1, expires_days: int = 14) -> dict:
    """(org_admin) Mint an invite code so a new person can self-register. role:
    member | maintainer | org_admin. Returns the code — share it; the invitee registers
    with it and gets a token carrying that role. This is how the first admin onboards
    everyone else, straight from Claude."""
    with _authed() as (session, account):
        return org_service.create_invite(session, account, role, uses, expires_days)


@mcp.tool
def hive_members() -> list[dict]:
    """(org_admin) List the people in your org with their role and active token count —
    use it to decide who to promote or demote."""
    with _authed() as (session, account):
        return org_service.list_members(session, account)


@mcp.tool
def hive_delete(node_uid: str) -> dict:
    """(org_admin) Permanently delete a knowledge node — its files and any chores about
    it go too. This is the admin escape hatch from consensus-gated mutation: use it to
    prune wrong or obsolete memories. Audited; cannot be undone."""
    with _authed() as (session, account):
        return governance_service.admin_delete(session, account, node_uid)


@mcp.tool
def hive_set_password(password: str) -> dict:
    """Set/change the password on YOUR account so you can log into the GUI with username +
    password (minimum 8 chars). The account name is your username."""
    with _authed() as (session, account):
        from src.services import auth_service
        return auth_service.set_own_password(session, account, password)


@mcp.tool
def hive_set_system(node_uid: str, on: bool = True) -> dict:
    """(org_admin) Mark a node as a SYSTEM memory — it is then injected into EVERY recall
    on every prompt for every connected client, regardless of relevance. Use it for
    standing instructions (e.g. 'how to work with the HiveMind') so guidance is always
    present and centrally updatable (edit the node → all clients get it next prompt).
    Set on=False to unpin."""
    with _authed() as (session, account):
        return governance_service.set_system(session, account, node_uid, on)


@mcp.tool
def hive_set_role(account_name: str, role: str) -> dict:
    """(org_admin) Promote or demote a person by account name: member | maintainer |
    org_admin. The role is applied to their account and all their tokens."""
    with _authed() as (session, account):
        return org_service.set_role(session, account, account_name, role)


@mcp.tool
def session_save(name: str, state: str) -> dict:
    """Save (or overwrite) a working-session snapshot in the hive under `name`, bound to
    YOUR account. Put whatever a future session needs to continue: the goal, what's done,
    current step, open questions, key file paths/decisions. Resume it later with
    session_resume — from any device, as long as you use a token for the same account."""
    with _authed() as (session, account):
        return session_repo.save(session, account, name, state)


@mcp.tool
def session_list() -> list[dict]:
    """List your saved session snapshots (name, last updated, size) — bound to your account."""
    with _authed() as (session, account):
        return session_repo.list_for(session, account)


@mcp.tool
def session_resume(name: str) -> dict:
    """Load a saved session snapshot to continue where it left off (bound to your account)."""
    with _authed() as (session, account):
        data = session_repo.get(session, account, name)
        if data is None:
            raise ValueError(f"No saved session '{name}' for this account")
        return data


@mcp.tool
def session_delete(name: str) -> dict:
    """Delete a saved session snapshot (bound to your account)."""
    with _authed() as (session, account):
        if not session_repo.delete(session, account, name):
            raise ValueError(f"No saved session '{name}' for this account")
        return {"deleted": True, "name": name}


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
        node["files"] = graph_repo.node_files(session, account, skill_uid)
        return node


@mcp.tool
def hive_update() -> dict:
    """Update this project's HiveMind client integration to the latest maintained version.
    Returns a self-describing manifest with `apply_instructions` and two parts:
    - `files`: the helper scripts (each with target `path`, `purpose`, `mode`, `sha256`,
      full `content`) — create missing, overwrite where the local sha differs, leave equal
      ones, make 0755 executable.
    - `config`: the Claude-side wiring to reconcile — the recall hook in
      .claude/settings.json and the MCP server in .mcp.json — described declaratively as
      requirements. Fix only what is missing/wrong and PRESERVE all secrets (HIVE_TOKEN,
      HIVE_URL, Authorization, the MCP url); never overwrite or print them.
    Does not manage CLAUDE.md (instructions arrive via the recall system memory). After
    applying, report what you added/updated/left unchanged for both files and config.
    Use this whenever the user asks to update/refresh HiveMind — no local script needed."""
    with _authed() as (session, account):
        return kit_service.build_manifest()
