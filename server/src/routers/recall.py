from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.components.db import get_graph
from src.repository import focus_repo, governance_repo, graph_repo
from src.models.core import RecallRequest, RecallResponse
from src.services import governance_service, search_service

router = APIRouter(tags=["hive"])


@router.post("/recall", response_model=RecallResponse)
def recall(
    body: RecallRequest,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Deterministic read side: called by the plugin's UserPromptSubmit hook on every
    prompt. Anchors (the project's topics, via HIVE_ANCHORS) boost the project's slice
    of the Hive in the ranking without hiding the rest of the org's knowledge. One
    contextually-matched Pollen (task) piggybacks so every model in the Swarm carries a
    bit of pollen each visit — strengthening Nectar as it goes."""
    results = search_service.search(
        session, account, body.query, anchors=body.anchors or None, limit=body.limit
    )

    # System memories: standing instructions always injected, on top, regardless of query.
    system = graph_repo.list_system(session, account)
    seen = {n["uid"] for n in system}
    results = [n for n in results if n["uid"] not in seen]

    ready = governance_repo.ready_count(session, account)
    parts = []
    # Active focus first: the current task/plan/guardrails, re-injected every prompt to
    # keep a long session on course (anti-drift, survives compaction).
    focus = focus_repo.get_focus(session, account, project=body.project or "")
    if focus and focus.get("goal"):
        parts.append("## ▶ Actieve taak — blijf hierbij\n" + search_service.render_focus(focus))
    if system:
        parts.append("## Nectar — vaste instructies (altijd van toepassing)\n"
                     + search_service.render_system(system))
    if results:
        parts.append("## Nectar recall\n" + search_service.render_results(results))
    # One Pollen per visit: the single open/ready task most relevant to this prompt.
    pollen = governance_service.pick_contextual_pollen(session, account, body.query)
    if pollen:
        parts.append(governance_service.render_pollen(pollen))
    return RecallResponse(context="\n\n".join(parts), result_count=len(results), ready_chores=ready)
