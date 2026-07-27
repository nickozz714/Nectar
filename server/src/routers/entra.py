from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from neo4j import Session

from src.config import get_settings
from src.db.neo4j import get_graph
from src.services import entra_service

router = APIRouter(prefix="/auth/entra", tags=["auth"])


def _redirect_uri(request: Request) -> str:
    s = get_settings()
    if s.ENTRA_REDIRECT_URI:
        return s.ENTRA_REDIRECT_URI
    if s.PUBLIC_BASE_URL:
        return s.PUBLIC_BASE_URL.rstrip("/") + "/auth/entra/callback"
    return str(request.url_for("entra_callback"))


def _base(request: Request) -> str:
    s = get_settings()
    if s.PUBLIC_BASE_URL:
        return s.PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/status")
def status():
    """Whether Microsoft Entra SSO is configured — the GUI shows the button if enabled."""
    return {"enabled": get_settings().entra_enabled}


@router.get("/login")
def entra_login(request: Request):
    if not get_settings().entra_enabled:
        raise HTTPException(status_code=404, detail="Entra SSO not configured")
    return RedirectResponse(entra_service.login_url(_redirect_uri(request)))


@router.get("/callback", name="entra_callback")
def entra_callback(
    request: Request,
    code: str = "",
    state: str = "",
    session: Session = Depends(get_graph),
):
    if not get_settings().entra_enabled:
        raise HTTPException(status_code=404, detail="Entra SSO not configured")
    base = _base(request)
    try:
        result = entra_service.complete(session, code, state, _redirect_uri(request))
    except PermissionError as exc:
        return RedirectResponse(f"{base}/ui#error={quote(str(exc))}")
    # Hand the token back to the GUI via the URL fragment (never logged server-side).
    return RedirectResponse(f"{base}/ui#token={result['token']}")
