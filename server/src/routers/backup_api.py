from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.components.db import get_graph
from src.services import backup_service

# Whole-org backup & restore: one JSON document with every knowledge node, its edges and
# attachments (base64). org_admin-only; enforced in the service layer.
router = APIRouter(tags=["backup"])


@router.get("/export")
def export_backup(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Download the full org snapshot as a JSON file."""
    try:
        payload = backup_service.export_org(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="hivemind-backup-{stamp}.json"'},
    )


@router.post("/import")
async def import_backup(
    request: Request,
    mode: str = "merge",
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Restore a snapshot. ?mode=merge upserts (default); ?mode=replace wipes the org's
    knowledge first before importing."""
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    try:
        data = json.loads(await request.body())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
    try:
        result = backup_service.import_org(session, account, data, replace=(mode == "replace"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"mode": mode, "imported": result}
