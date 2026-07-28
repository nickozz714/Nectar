from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import get_graph
from src.repository import attachment_repo
from src.services import attachment_service

# Central artifact storage: attach a file to a memory so any machine can fetch it on demand.
# Upload = raw request body (curl --data-binary), so no multipart dependency.
router = APIRouter(tags=["attachments"])


@router.post("/graph/node/{uid}/attachments")
async def upload_attachment(
    uid: str,
    request: Request,
    filename: str = "bijlage",
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Attach the raw request body to a node. Pass ?filename=... and a Content-Type header."""
    data = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        return attachment_service.save(session, account, uid, filename, content_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/graph/node/{uid}/attachments")
def list_attachments(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """List attachment metadata (no bytes) for a node."""
    return attachment_repo.list_for(session, account, uid)


@router.get("/attachments/{att_uid}")
def download_attachment(
    att_uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Download an attachment's bytes (visibility follows the owning node)."""
    got = attachment_service.load(session, account, att_uid)
    if got is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    data, filename, content_type = got
    disposition = "attachment; filename*=UTF-8''" + urllib.parse.quote(filename)
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": disposition})


@router.delete("/attachments/{att_uid}")
def delete_attachment(
    att_uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    if not attachment_service.remove(session, account, att_uid):
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"deleted": True}
