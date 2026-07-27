from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import get_graph
from src.repository import governance_repo, graph_repo
from src.schemas.core import RecallRequest, RecallResponse
from src.services import search_service

router = APIRouter(tags=["hive"])


@router.post("/recall", response_model=RecallResponse)
def recall(
    body: RecallRequest,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Deterministic read side: called by the plugin's UserPromptSubmit hook on every
    prompt. Anchors (the project's topics, via HIVE_ANCHORS) boost the project's slice
    of the mind in the ranking without hiding the rest of the org's knowledge. Ready
    governance chores piggyback so a bee that is here anyway can pick one up."""
    results = search_service.search(
        session, account, body.query, anchors=body.anchors or None, limit=body.limit
    )

    # System memories: standing instructions always injected, on top, regardless of query.
    system = graph_repo.list_system(session, account)
    seen = {n["uid"] for n in system}
    results = [n for n in results if n["uid"] not in seen]

    ready = governance_repo.ready_count(session, account)
    parts = []
    if system:
        parts.append("## HiveMind — vaste instructies (altijd van toepassing)\n"
                     + search_service.render_results(system))
    if results:
        parts.append("## HiveMind recall\n" + search_service.render_results(results))
    if ready:
        parts.append(
            f"⚙ {ready} hive chore(s) ready for the swarm — when convenient, call "
            "hive_chores() and resolve one."
        )
    return RecallResponse(context="\n\n".join(parts), result_count=len(results), ready_chores=ready)
