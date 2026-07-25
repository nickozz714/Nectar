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


class AccountOut(BaseModel):
    uid: str
    name: str
    org_uid: str
    team_uid: str | None
    role: str


class TokenCreate(BaseModel):
    account_uid: str
    label: str | None = None
    expires_days: int | None = None


class TokenOut(BaseModel):
    token: str
    label: str | None


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


class RecallResponse(BaseModel):
    context: str
    result_count: int
    ready_chores: int
