from __future__ import annotations

from contextlib import contextmanager

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from src.authentication.deps import AuthedAccount, account_from_token
from src.components.db import graph_session
from src.repository import (
    attachment_repo, focus_repo, governance_repo, graph_repo, session_repo,
)
from src.services import (
    curation_service,
    governance_service,
    kit_service,
    memory_service,
    org_service,
    search_service,
    skill_service,
)

mcp = FastMCP(
    "Nectar",
    instructions=(
        "Nectar — the shared mind of your organization, usable from ANY MCP client. At the "
        "start of a task call hive_recall(<your task>) to load the relevant org knowledge "
        "(focus + standing instructions + top memories + one maintenance task). Write reusable "
        "knowledge back with hive_remember. Afterwards, hive_feedback(node_uid, helped) on what "
        "actually helped. When a Pollen (task) is ready, help maintain the hive."
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


def _project() -> str:
    """The current project slug, from the X-Hive-Project header set per project in .mcp.json.
    Empty when not project-scoped — so the active focus is bound to (account, project)."""
    try:
        return (get_http_request().headers.get("x-hive-project", "") or "").strip()
    except Exception:
        return ""


@mcp.tool
def hive_recall(query: str, anchors: list[str] | None = None, limit: int = 8,
                session: str = "") -> str:
    """Load the organization's relevant knowledge for your CURRENT task — the same context the
    Claude Code hook injects automatically, so ANY MCP client (Cursor, Cline, Windsurf, your own
    agent, …) can tap the shared brain the same way. Returns the active focus, the standing
    instructions, the top-ranked memories, and one contextual Pollen (maintenance task).

    Call this at the START of a task and whenever the topic shifts. Afterwards, tell the brain
    what actually helped with hive_feedback(node_uid, helped) so recall keeps improving. Pass
    `anchors` (your project's topic titles) to bias ranking toward that project. Pass `session`
    (your client's session id) to get YOUR focus lane instead of the project-wide focus — that
    is what lets several sessions run their own task in one project."""
    with _authed() as (graph, account):
        from src.services import recall_service
        return recall_service.recall(graph, account, query, anchors=anchors, limit=limit,
                                     project=_project(), session_id=session)["context"]


@mcp.tool
def hive_search(query: str, anchors: list[str] | None = None, limit: int = 8,
                tags: list[str] | None = None) -> str:
    """Search the hive's shared memory. Results are ranked by semantic relevance and
    freshness (recently-used knowledge first). Pass `anchors` (topic titles, e.g. your
    project's topics from HIVE_ANCHORS) to boost that slice of the mind in the ranking —
    a preference, not a filter: knowledge from other contexts stays findable and may
    still be the answer. Pass `tags` to restrict to nodes carrying ALL those tags; a node
    whose tag also appears in the query gets a ranking nudge. Reading a memory rejuvenates it."""
    with _authed() as (session, account):
        results = search_service.search(session, account, query, anchors=anchors, limit=limit, tags=tags)
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
        attachments = attachment_repo.list_for(session, account, node_uid)
        if attachments:
            node["attachments"] = attachments  # metadata only; fetch bytes via /attachments/{uid}
        graph_repo.touch_nodes(session, [node_uid])
        return node


@mcp.tool
def hive_claim(pollen_uid: str) -> dict:
    """Claim a Pollen (task) before you start working it, so other agents in the Swarm skip it
    and don't duplicate your work (stigmergy). The claim auto-expires after a while. Call
    hive_release if you decide not to do it. Returns {claimed:true} or notes another agent holds it."""
    from src.components.config import get_settings
    with _authed() as (session, account):
        res = graph_repo_governance_claim(session, account, pollen_uid)
        return res


@mcp.tool
def hive_release(pollen_uid: str) -> dict:
    """Release a Pollen you claimed but won't finish, so another agent can pick it up."""
    with _authed() as (session, account):
        from src.repository import governance_repo
        ok = governance_repo.release_pollen(session, account.org_uid, pollen_uid, account.uid)
        return {"released": ok}


def graph_repo_governance_claim(session, account, pollen_uid: str) -> dict:
    from src.components.config import get_settings
    from src.repository import governance_repo
    res = governance_repo.claim_pollen(session, account.org_uid, pollen_uid, account.uid,
                                        get_settings().CLAIM_TTL_MIN)
    if res is None:
        return {"claimed": False, "note": "Another agent holds an active claim on this Pollen — pick a different one."}
    return {"claimed": True, "pollen_uid": pollen_uid}


@mcp.tool
def hive_resolve_think(pollen_uid: str, decision: str, merged_title: str = "",
                       merged_content: str = "", note: str = "") -> dict:
    """Do the reasoning an op_route think-Pollen asks for: two near-duplicate memories, decide
    how to reconcile them. decision is one of:
      • ADD — they are genuinely distinct, keep both
      • UPDATE — merge into one better memory (supply merged_title + merged_content); the new
        one is archived and the merged memory is confirmed 'validated'
      • REPLACE — the new memory is the current truth; supersede the existing one (new wins, old
        stays findable but sinks)
      • DELETE — the new memory is a duplicate, archive it
      • NOOP — leave as-is
    If the payload has merge_requested=true, a human asked for a merge → do an UPDATE.
    SAFEGUARD: ADD/NOOP may be decided by any member. UPDATE/DELETE/REPLACE may not be done by
    the account that wrote the new memory — a different Swarm member must judge it — unless
    that account holds org_admin (an admin reviewer may always resolve). Read both memories
    with hive_get first."""
    with _authed() as (session, account):
        from src.services import governance_service
        return governance_service.resolve_think(
            session, account, pollen_uid, decision, merged_title, merged_content, note)


@mcp.tool
def hive_resolve_contradiction(pollen_uid: str, verdict: str, current: str = "",
                               outdated: str = "", note: str = "") -> dict:
    """Judge a contradiction-check think-Pollen: two highly-similar memories — do they CONTRADICT
    (a different decision/value for the same thing)? Read both with hive_get first.
      • verdict="compatible" — they don't conflict; close it.
      • verdict="contradiction" — they conflict; pass current=<uid of the memory that is the
        current truth> and outdated=<uid of the old one>. The outdated one is superseded (stays
        findable but sinks in recall; the current wins)."""
    with _authed() as (session, account):
        from src.services import governance_service
        return governance_service.resolve_contradiction(
            session, account, pollen_uid, verdict, current, outdated, note)


@mcp.tool
def hive_resolve_cognition(pollen_uid: str, summary: str, created_uids: list[str] | None = None,
                           follow_up: list[dict] | None = None, note: str = "") -> dict:
    """Close a cognition-Pollen after doing its research. The task: extract the named entities
    from the memory the Pollen is about, hive_search each — if the hive already knows it, at
    most hive_relate it; if unknown, look it up on the web and write ONE compact glossary
    entry (type='glossary', 2-5 sentences, source URLs, tags=['world-knowledge'], same scope
    as the source) via hive_remember, then hive_relate it to the source. Stay within the budget
    (payload.budget.max_new memories).
      • summary — one or two sentences on what was researched and found
      • created_uids — the uids of the reference memories you wrote (provenance)
      • follow_up — [{node_uid, question}] for at most one genuinely interesting next-round
        question per new node (e.g. 'which other brands does Swinkels own?'); the server files
        it as a next-round cognition-Pollen and refuses it beyond the budget's max_depth.
    'Nothing unknown found' with empty created_uids is a perfectly good resolution."""
    with _authed() as (session, account):
        from src.services import governance_service
        return governance_service.resolve_cognition(
            session, account, pollen_uid, summary, created_uids, follow_up, note)


@mcp.tool
def hive_feedback(node_uid: str, helped: bool) -> dict:
    """Report whether a memory you recalled actually helped with your task (helped=true) or
    was wrong/irrelevant (helped=false). This is the causal 'Memory Worth' signal: memories
    that consistently help rise in recall, ones that consistently mislead sink. Call it after
    you applied (or rejected) a recalled memory — a small pollen every visit."""
    with _authed() as (session, account):
        res = graph_repo.record_feedback(session, account.org_uid, node_uid, helped)
        if res is None:
            raise ValueError("Node not found or not visible to this account")
        return res


@mcp.tool
def hive_attachments(node_uid: str) -> list[dict]:
    """List the artifacts (files) attached to a node — filename, size, type, uid. Attachments
    live centrally in the hive, so a machine that did not create them can still get them.
    Download one to the local machine with the bundled helper:
    `~/.hivemind/scripts/hive-attach get <attachment_uid> [outfile]` (or GET /attachments/{uid}
    with your bearer). Add one with `hive-attach add <node_uid> <path>`."""
    with _authed() as (session, account):
        return attachment_repo.list_for(session, account, node_uid)


@mcp.tool
def hive_remember(
    type: str,
    title: str,
    content: str,
    parent_topics: list[str],
    scope: str = "team",
    model_name: str = "",
    force: bool = False,
    tags: list[str] | None = None,
    parent_node: str = "",
) -> dict:
    """Write reusable knowledge into the hive. type: memory | process | workflow |
    convention | decision | glossary | learning (for file-backed skills/workflows use skill_put /
    workflow_put). Set force=True to create anyway when a previous call was rejected as a
    near-duplicate but it is genuinely new (a dedup false positive). Link it under parent topics
    (subjects, projects or systems — e.g. 'Data Modelling', 'Swinkels'); semantically
    similar existing topics are reused, only then is a new topic created. scope: team
    (default), org, or account. The write-gate enforces: specific title, self-contained
    content, no personal data (PII), and dedup — hard duplicates are rejected, close
    lookalikes are created but flagged as a dedup chore for the swarm. Pass model_name
    (your model id) for provenance. Only store knowledge that is reusable for the
    organization — no session noise. `tags` are short labels that also count in search.
    `parent_node` (a node uid) hangs this node as a CONTAINS child of that memory/skill/workflow."""
    with _authed() as (session, account):
        return memory_service.remember(
            session, account, type, title, content, parent_topics, scope, model_name, force,
            tags, parent_node
        )


@mcp.tool
def hive_learn(
    title: str,
    content: str,
    parent_node: str = "",
    parent_topics: list[str] | None = None,
    tags: list[str] | None = None,
    scope: str = "team",
    model_name: str = "",
) -> dict:
    """Record a LEARNING — a hard-won lesson that must always surface with high priority
    (e.g. a mistake and how to avoid it, a non-obvious gotcha). Learnings get a strong recall
    boost and decay slowly. Optionally hang it as a child of the memory, skill or workflow it
    came from via `parent_node` (that node's uid). Keep it self-contained: what went wrong /
    what we learned, and what to do instead."""
    with _authed() as (session, account):
        return memory_service.remember(
            session, account, "learning", title, content, parent_topics or [], scope,
            model_name, False, tags, parent_node
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
    standing instructions (e.g. 'how to work with the Nectar') so guidance is always
    present and centrally updatable (edit the node → all clients get it next prompt).
    Set on=False to unpin."""
    with _authed() as (session, account):
        return governance_service.set_system(session, account, node_uid, on)


@mcp.tool
def hive_set_cognition(on: bool = True) -> dict:
    """(org_admin) Toggle cognition-Pollen for the org: optional world research on newly
    written memories. When on, every new memory/learning/decision gets a 'research the
    unknown concepts' Pollen that a swarm agent works via hive_resolve_cognition. Off by
    default — it costs web searches and tokens; a budget (memories per job, follow-up
    rounds, daily cap) bounds the curiosity."""
    with _authed() as (session, account):
        return org_service.set_cognition_enabled(session, account, on)


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
def focus_set(goal: str, steps: list, guardrails: list[str] | None = None,
              done_when: str = "", session: str = "", name: str = "") -> dict:
    """Set (or replace) your ACTIVE FOCUS: the current multi-step task. It is re-injected at
    the top of recall on EVERY prompt, so it stays in the model's high-attention zone and
    survives compaction — the fix for long sessions drifting off-course. Use it whenever a
    task needs several steps or has constraints worth holding.
    - goal: one sentence — what we're achieving.
    - steps: ordered list of short step strings (the first becomes the current step).
    - guardrails: hard do/don't rules that prevent drift, e.g. "work in the BACKEND via the
      API; the frontend is only for step 3 (a few clicks), nothing else there".
    - done_when: how you know it's finished.
    - session: YOUR LANE TOKEN — the `sessiebaan`/`baan` token printed in your recall block.
      ALWAYS pass it: it gives this session its own focus lane, so parallel sessions working
      different tasks in the SAME project don't overwrite each other's focus. Omit it only if
      you deliberately want the single project-wide focus that every session sees.
    - name: optional human name for the lane ("ollama-migratie"). Pass it together with
      `session` to join/resume an existing named lane (e.g. after a /clear gave you a new
      session), or just to label your lane in the GUI.
    Update progress with focus_advance (same `session`); clear it with focus_clear when done.
    See the lanes running in this project with focus_list."""
    with _authed() as (graph, account):
        if not goal.strip():
            raise ValueError("goal is required")
        return focus_repo.set_focus(graph, account, goal, steps, guardrails,
                                    done_when, project=_project(),
                                    session_id=session, name=name)


@mcp.tool
def focus_advance(completed_step: str | int | None = None, note: str | None = None,
                  session: str = "", name: str = "") -> dict:
    """Update your active focus as you make progress: mark a step done (by its 1-based number
    or its text) — the next open step becomes current — and/or append a short progress note.
    Call this at the end of each step so the re-injected plan always reflects where you are.
    Pass `session` (your lane token from the recall block) so you update YOUR lane and not a
    parallel session's focus; `name` addresses a named lane instead."""
    with _authed() as (graph, account):
        updated = focus_repo.advance_focus(graph, account, completed_step, note,
                                           project=_project(), session_id=session, name=name)
        if updated is None:
            raise ValueError("No active focus for this lane — set one with focus_set first")
        return updated


@mcp.tool
def focus_get(session: str = "", name: str = "") -> dict:
    """Return your current active focus (goal, steps with status, guardrails, notes). Pass
    `session` (your lane token) for YOUR lane, or `name` for a named lane; without either you
    get the project-wide focus."""
    with _authed() as (graph, account):
        focus = focus_repo.get_focus(graph, account, project=_project(),
                                     session_id=session, name=name)
        if focus is None:
            return {"active": False}
        return {"active": True, **focus}


@mcp.tool
def focus_list() -> list[dict]:
    """List every active focus LANE in this project — what each parallel session in this
    project is working on. Use it to avoid colliding with a sibling session, or to find the
    lane name to resume with focus_set(..., name=...)."""
    with _authed() as (graph, account):
        return focus_repo.list_for(graph, account, project=_project())


@mcp.tool
def focus_clear(session: str = "", name: str = "", all_lanes: bool = False) -> dict:
    """Clear your active focus — the task is done or abandoned, stop re-injecting it. Pass
    `session` (your lane token) to clear only YOUR lane, `name` for a named lane, or
    all_lanes=True to wipe every lane in this project."""
    with _authed() as (graph, account):
        removed = focus_repo.clear_focus(graph, account, project=_project(),
                                         session_id=session, name=name, all_lanes=all_lanes)
        return {"cleared": removed > 0, "removed": removed}


@mcp.tool
def topic_list() -> list[dict]:
    """List the visible topic nodes (the top of the mind) with their child counts. Use
    to orient, to pick anchors, or to decide where new knowledge belongs."""
    with _authed() as (session, account):
        return graph_repo.list_topics(session, account)


@mcp.tool
def topic_create(title: str, parent_topic: str = "") -> dict:
    """Create a topic to organise the mind (reuses an existing topic with the same title).
    Optionally nest it under a parent topic, e.g. topic_create('Gemeentelijk Gegevens Model
    (GGM)', parent_topic='Data Modelling')."""
    with _authed() as (session, account):
        return curation_service.create_topic(session, account, title, parent_topic)


@mcp.tool
def topic_merge(from_topic: str, into_topic: str) -> dict:
    """Merge one topic into another (maintainer): moves all children of `from_topic` under
    `into_topic` and deletes the empty source. Use to dedupe split topics, e.g.
    topic_merge('GGM', 'Gemeentelijk Gegevens Model (GGM)')."""
    with _authed() as (session, account):
        return curation_service.merge_topics(session, account, from_topic, into_topic)


@mcp.tool
def node_move(node_uid: str, to_topic: str, keep_others: bool = False) -> dict:
    """Re-hang a node under a different topic (maintainer role). By default this REPLACES the
    node's topic parents; keep_others=True adds the new topic while keeping existing ones
    (multi-parent). The target topic is created if needed. E.g. move the 'ggm-export' skill
    from 'Gemeente Krimpenerwaard' to 'Gemeentelijk Gegevens Model (GGM)'."""
    with _authed() as (session, account):
        return curation_service.move_node(session, account, node_uid, to_topic, keep_others)


@mcp.tool
def hive_tag(node_uid: str, add: list[str] | None = None, remove: list[str] | None = None) -> dict:
    """Add and/or remove tags on a node. Tags are short lowercase labels that also count in
    search (a query mentioning a tag boosts tagged nodes; hive_search(tags=[...]) filters)."""
    with _authed() as (session, account):
        return curation_service.set_tags(session, account, node_uid, add=add, remove=remove)


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
    """Update this project's Nectar client integration to the latest maintained version.
    Returns a self-describing manifest with `apply_instructions` and two parts:
    - `files`: the helper scripts (each with target `path`, `sha256`, and a `fetch` URL) —
      apply them by FETCHING, not by re-typing their bodies. Simplest: run
      `bash ~/.hivemind/scripts/hive-update.sh`; if that script is missing, run the
      `bootstrap` one-liner from the manifest. The bytes flow curl→disk, so an update is
      fast and byte-exact — reproducing script contents in the conversation is unnecessary
      and risks transcription errors (verify with the per-file `sha256` if you want).
    - `config`: the Claude-side wiring to reconcile — the recall hook in
      .claude/settings.json and the MCP server in .mcp.json — described declaratively as
      requirements. Fix only what is missing/wrong and PRESERVE all secrets (HIVE_TOKEN,
      HIVE_URL, Authorization, the MCP url); never overwrite or print them.
    Does not manage CLAUDE.md (instructions arrive via the recall system memory). After
    applying, report what you added/updated/left unchanged for both files and config.
    Use this whenever the user asks to update/refresh Nectar — no local script needed."""
    with _authed() as (session, account):
        return kit_service.build_manifest()
