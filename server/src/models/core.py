from __future__ import annotations

from pydantic import BaseModel


class OrgCreate(BaseModel):
    name: str


class OrgOut(BaseModel):
    uid: str
    name: str


class TeamCreate(BaseModel):
    org_uid: str
    name: str


class TeamOut(BaseModel):
    uid: str
    name: str
    org_uid: str


class AccountCreate(BaseModel):
    org_uid: str
    name: str
    team_uid: str | None = None
    role: str = "member"
    person: str | None = None  # the human accountable for this account
    email: str | None = None


class OrgAccountCreate(BaseModel):
    """Create an account inside the caller's OWN org (org_uid comes from the session token,
    not the body) — used by org_admins via /manage, no operator admin token needed."""
    name: str
    team_uid: str | None = None
    role: str = "member"
    person: str | None = None
    email: str | None = None


class AccountOut(BaseModel):
    uid: str
    name: str
    org_uid: str
    team_uid: str | None
    role: str
    person: str | None = None
    email: str | None = None


class RegisterBody(BaseModel):
    name: str
    email: str | None = None
    invite_code: str | None = None


class InviteCreate(BaseModel):
    role: str = "member"
    uses: int = 1
    expires_days: int | None = 14


class TokenRoleBody(BaseModel):
    role: str


class TokenCreate(BaseModel):
    account_uid: str
    label: str | None = None
    expires_days: int | None = None
    role: str | None = None


class TokenOut(BaseModel):
    token: str
    label: str | None = None
    role: str | None = None


class SecretGrantCreate(BaseModel):
    org_uid: str
    name: str
    account_uid: str


class ChoreDecision(BaseModel):
    note: str = ""


class ChoreOut(BaseModel):
    uid: str
    type: str
    payload: str | None = None
    org_uid: str | None = None
    node_uid: str | None = None
    node_title: str | None = None
    node_scope: str | None = None
    votes: list[dict] | None = None


class RecallRequest(BaseModel):
    query: str
    anchors: list[str] = []
    limit: int = 8
    project: str = ""  # project slug (HIVE_PROJECT) — scopes the active focus


class RecallResponse(BaseModel):
    context: str
    result_count: int
    ready_chores: int
