from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import get_graph
from src.services import vault_service

router = APIRouter(prefix="/secrets", tags=["vault"])


@router.get("/{name}", response_model=dict)
def get_secret(
    name: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Deliberately REST-only (no MCP tool): secrets are fetched by scripts for env
    injection and must never end up in chat context. Every read is audited."""
    value = vault_service.get_secret(session, account, name)
    if value is None:
        raise HTTPException(status_code=404, detail="Secret not found or no grant")
    return {"name": name, "value": value}


@router.put("/{name}", response_model=dict)
def set_secret(
    name: str,
    body: dict,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    value = body.get("value")
    if not value:
        raise HTTPException(status_code=400, detail="body must contain 'value'")
    try:
        return vault_service.set_secret(session, account, name, value)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
