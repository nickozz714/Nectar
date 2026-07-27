from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session
from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, require_account, require_role
from src.db.neo4j import get_graph
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    name: str
    password: str


class PasswordBody(BaseModel):
    password: str


class SetPasswordForBody(BaseModel):
    name: str
    password: str


@router.post("/login")
def login(body: LoginBody, session: Session = Depends(get_graph)):
    """Log in with username + password → returns an account token for the GUI/clients."""
    try:
        return auth_service.login(session, body.name, body.password)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/password")
def set_own_password(
    body: PasswordBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Set/change your own password (you're already authenticated with a token)."""
    try:
        return auth_service.set_own_password(session, account, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/password/for")
def set_password_for(
    body: SetPasswordForBody,
    account: AuthedAccount = Depends(require_role("org_admin")),
    session: Session = Depends(get_graph),
):
    """org_admin: set/reset a password for another account in the org."""
    try:
        return auth_service.set_password_for(session, account, body.name, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
