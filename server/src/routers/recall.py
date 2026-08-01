from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.components.db import get_graph
from src.models.core import RecallRequest, RecallResponse
from src.services import recall_service

router = APIRouter(tags=["hive"])


@router.post("/recall", response_model=RecallResponse)
def recall(
    body: RecallRequest,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Deterministic read side: called by the Claude Code plugin's UserPromptSubmit hook on every
    prompt. Composes the recall context (focus + standing instructions + ranked memories + one
    contextual Pollen). Other MCP clients get the same via the hive_recall tool. Anchors boost the
    project's slice of the Hive without hiding the rest of the org's knowledge."""
    r = recall_service.recall(
        session, account, body.query, anchors=body.anchors or None,
        project=body.project or "", limit=body.limit,
    )
    return RecallResponse(context=r["context"], result_count=r["result_count"],
                          ready_chores=r["ready_chores"])
