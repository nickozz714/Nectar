from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session
from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, require_account
from src.components.db import get_graph
from src.repository import graph_repo
from src.services import skill_service

# HTTP access to shared skills, so a Claude Code CLI (or the installer helper) can fetch — and
# now also publish — a skill over plain HTTP, no MCP needed.
router = APIRouter(prefix="/skills", tags=["skills"])


class SkillFile(BaseModel):
    path: str
    content: str


class SkillBody(BaseModel):
    title: str
    description: str = ""
    files: list[SkillFile]
    parent_topics: list[str] = []
    scope: str = "org"


@router.get("")
def list_skills(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """List the shared skills visible to the caller (uid + title)."""
    return graph_repo.list_skills(session, account)


@router.post("")
def put_skill(
    body: SkillBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Create or update a file-backed skill (needs a SKILL.md). Same write-gate + consensus rules
    as the MCP skill_put: you may update your own skill directly; editing someone else's goes
    through hive_suggest."""
    try:
        return skill_service.put_skill(
            session, account, body.title, body.description,
            [f.model_dump() for f in body.files], body.parent_topics, body.scope, "gui",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{uid}")
def get_skill(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Fetch one skill plus its files ({path, content}) in Claude Code skill format."""
    node = graph_repo.get_node(session, account, uid)
    if node is None or node.get("type") != "skill":
        raise HTTPException(status_code=404, detail="Skill not found or not visible")
    return {
        "uid": node["uid"],
        "title": node.get("title"),
        "description": node.get("description"),
        "files": graph_repo.node_files(session, account, uid),
    }
