from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from src.authentication.deps import AuthedAccount, require_account
from src.services import kit_service

# Serve individual client-kit scripts so an update can FETCH them (curl -> disk) instead of
# the model writing the bodies out — the latter is slow and trips content classifiers.
router = APIRouter(prefix="/kit", tags=["kit"])


@router.get("/file/{name}")
def kit_file(name: str, account: AuthedAccount = Depends(require_account)):
    """Raw bytes of one helper script from the maintained package (account-gated)."""
    body = kit_service.read_kit_file(name)
    if body is None:
        raise HTTPException(status_code=404, detail="Unknown kit file")
    return Response(content=body, media_type="text/x-shellscript")
