from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import get_graph
from src.repository import graph_repo

# Read-only HTTP access to shared skills, so a Claude Code CLI (or the installer helper)
# can fetch a skill and drop it into .claude/skills/ over plain HTTP — no MCP needed.
router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("")
def list_skills(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """List the shared skills visible to the caller (uid + title)."""
    return graph_repo.list_skills(session, account)


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
