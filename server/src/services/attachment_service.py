from __future__ import annotations

import base64
import hashlib

from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.config import get_settings
from src.repository import attachment_repo, audit_repo


def save(
    session: Session, account: AuthedAccount, node_uid: str,
    filename: str, content_type: str, data: bytes,
) -> dict:
    max_bytes = get_settings().ATTACHMENT_MAX_MB * 1024 * 1024
    if not data:
        raise ValueError("Empty upload")
    if len(data) > max_bytes:
        raise ValueError(f"Attachment too large (max {get_settings().ATTACHMENT_MAX_MB} MB) — "
                         "link to it instead of attaching")
    meta = attachment_repo.add(
        session, account, node_uid,
        filename=(filename or "bijlage").strip(),
        content_type=content_type or "application/octet-stream",
        data_b64=base64.b64encode(data).decode(),
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    if meta is None:
        raise ValueError("Node not found or not visible")
    audit_repo.log(session, account.org_uid, account.uid, "attach", node_uid,
                   {"filename": meta["filename"], "size": meta["size"], "attachment": meta["uid"]})
    return meta


def load(session: Session, account: AuthedAccount, att_uid: str) -> tuple[bytes, str, str] | None:
    """Return (bytes, filename, content_type) for a visible attachment, or None."""
    row = attachment_repo.get(session, account, att_uid)
    if row is None:
        return None
    return base64.b64decode(row["data"]), row["filename"], row["content_type"]


def remove(session: Session, account: AuthedAccount, att_uid: str) -> bool:
    node_uid = attachment_repo.delete(session, account, att_uid)
    if node_uid is None:
        return False
    audit_repo.log(session, account.org_uid, account.uid, "attach_delete", node_uid,
                   {"attachment": att_uid})
    return True
