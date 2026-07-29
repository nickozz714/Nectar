from __future__ import annotations

import time

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.repository import backup_repo

EXPORT_VERSION = 1


def export_org(session: Session, account: AuthedAccount) -> dict:
    """Full JSON snapshot of the caller's org knowledge graph. org_admin only."""
    assert_role(account, "org_admin", "Exporting a backup")
    payload = backup_repo.export_all(session, account.org_uid)
    return {
        "hivemind_export": EXPORT_VERSION,
        "exported_at": int(time.time()),
        "org_uid": account.org_uid,
        "counts": {k: len(v) for k, v in payload.items()},
        **payload,
    }


def import_org(session: Session, account: AuthedAccount, data: dict, *, replace: bool) -> dict:
    """Restore a snapshot into the caller's org. `replace` wipes the org's knowledge first
    (true restore); otherwise it upserts (merge). org_admin only."""
    assert_role(account, "org_admin", "Importing a backup")
    if int(data.get("hivemind_export", 0)) != EXPORT_VERSION:
        raise ValueError("Unrecognised backup format (missing/incompatible 'hivemind_export' version)")
    if replace:
        backup_repo.wipe(session, account.org_uid)
    return backup_repo.import_all(session, account.org_uid, data)
