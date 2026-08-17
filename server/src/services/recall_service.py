from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.repository import focus_repo, governance_repo, graph_repo
from src.services import governance_service, search_service


def recall(
    session: Session,
    account: AuthedAccount,
    query: str,
    anchors: list[str] | None = None,
    project: str = "",
    limit: int = 8,
    session_id: str = "",
) -> dict:
    """Compose the full recall context for a task — the same block the Claude Code hook injects
    automatically, now shared so ANY MCP client can pull it on demand via the hive_recall tool:
    the active focus, the standing (system) instructions, the top-ranked memories, and one
    contextually-matched Pollen. Client-agnostic — the brain speaks plain MCP."""
    results = search_service.search(session, account, query, anchors=anchors or None, limit=limit)
    if not results:
        # A recall that found nothing is a knowledge gap — aggregate it so repeated
        # unanswered questions surface as capture prompts (self-improving loop).
        graph_repo.record_gap(session, account.org_uid, query)

    # System memories: standing instructions always injected, on top, regardless of query.
    system = graph_repo.list_system(session, account)
    seen = {n["uid"] for n in system}
    results = [n for n in results if n["uid"] not in seen]
    # Anti context-rot: inject only a few, highly-relevant memories, strongest at the ends.
    results = search_service.cap_and_order(results)
    # Log what was actually shown (with its ranking features) as an impression — becomes a
    # labeled training example for learning-to-rank once the agent gives feedback on it.
    graph_repo.record_impressions(session, account.org_uid,
                                  [{"uid": n["uid"], "features": n["_feat"]} for n in results if n.get("_feat")])

    ready = governance_repo.ready_count(session, account)
    parts: list[str] = []
    # Active focus first: the current task/plan/guardrails, kept in the high-attention zone.
    # Resolved per LANE: with a session id the caller sees ITS OWN focus, so several sessions can
    # work different tasks in one project without overwriting each other. No lane of its own ->
    # the project-wide focus (lane ""), the original behaviour.
    token = focus_repo.session_token(session_id)
    focus = focus_repo.get_focus(session, account, project=project or "", session_id=session_id)
    if focus and focus.get("goal"):
        head = "## ▶ Actieve taak — blijf hierbij"
        lane_name = focus.get("label") or (focus["lane"] if focus["lane"] else "")
        if lane_name:
            head += f" (baan: {lane_name})"
        parts.append(head + "\n" + search_service.render_focus(focus, session_token=token))
        if token:
            focus_repo.touch(session, account, project or "", focus["lane"])
    elif token and project:
        # No focus yet: hand the session its lane token so the focus it sets is ITS OWN and a
        # parallel session in this project can't overwrite it.
        parts.append(
            f"_Sessiebaan `{token}` (project `{project}`) — leg een taak met meerdere stappen "
            f"vast met `focus_set(..., session=\"{token}\")`, dan houdt elke parallelle sessie "
            "in dit project zijn eigen focus._")
    if token:
        focus_repo.prune_stale(session, account)
    if system:
        parts.append("## Nectar — vaste instructies (altijd van toepassing)\n"
                     + search_service.render_system(system))
    if results:
        parts.append("## Nectar recall\n" + search_service.render_results(results))
    pollen = governance_service.pick_contextual_pollen(session, account, query)
    if pollen:
        parts.append(governance_service.render_pollen(pollen))

    return {"context": "\n\n".join(parts), "result_count": len(results), "ready_chores": ready}
