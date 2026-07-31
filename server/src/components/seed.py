from __future__ import annotations

import re
from pathlib import Path

from neo4j import Session

from src.repository import graph_repo, tenancy_repo

# System-level content (the always-injected "how to work with Nectar" instructions) is
# maintained IN THE REPO, not by hand in the hive. This file is the single source of truth;
# on startup the seed upserts it as a SYSTEM memory in every org. Edit the .md + redeploy.
_SEED_KEY = "hive-usage-instructions"
_SEED_FILE = Path(__file__).resolve().parents[1] / "seed" / "system_instructions.md"


def load_seed() -> tuple[str, str]:
    """Return (title, content) from the seed markdown: the first H1 is the title, the
    body is everything after it minus the maintainer HTML comment."""
    text = _SEED_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:])
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    return title, body


def seed_org(session: Session, org_uid: str) -> dict:
    title, content = load_seed()
    return graph_repo.upsert_system_seed(
        session, org_uid, _SEED_KEY, "convention", title, content
    )


def seed_all(session: Session) -> int:
    """Seed/refresh the system instructions in every existing org. Idempotent."""
    orgs = tenancy_repo.list_orgs(session)
    for o in orgs:
        seed_org(session, o["uid"])
    return len(orgs)
