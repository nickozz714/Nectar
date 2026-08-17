from __future__ import annotations

import json
import re

from neo4j import Session

from src.authentication.deps import AuthedAccount

# The ACTIVE FOCUS: a living task per LANE that the recall hook re-injects on every prompt, so a
# long session doesn't drift or lose the plan after compaction. Its own label (:HiveFocus) so it
# never leaks into shared recall/search — it is steering state, not knowledge.
#
# Keyed by (account_uid, project, lane). A LANE is what lets SEVERAL sessions run their own task
# in the SAME project without overwriting each other: the recall hook sends the client's session
# id, the server stores a short token for it in f.sessions, and every focus call resolves the
# caller's lane from that token. Optionally a lane carries a human name (label) so a session can
# join or resume a named lane (e.g. after /clear). lane "" is the project-wide focus a client
# without a session token gets — the original single-focus behaviour, unchanged.
#
# Steps are a JSON string (Neo4j has no list-of-maps); guardrails/notes/sessions are native lists.

_STATUSES = ("done", "current", "open")
STALE_LANE_DAYS = 21  # a session lane nobody recalled for this long is a leftover; pruned


def session_token(session_id: str) -> str:
    """Short, stable token for a client session: the first 8 alphanumerics of its session id.
    Short enough for a model to copy out of its recall block, unique enough within one account.
    Accepts a token that was already shortened (idempotent)."""
    return re.sub(r"[^a-z0-9]", "", (session_id or "").strip().lower())[:8]


def _lane_slug(name: str) -> str:
    """A lane's key from its human name — so 'Ollama migratie' and 'ollama-migratie' are one lane."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")[:40]


def _normalize_steps(steps: list) -> list[dict]:
    """Accept a list of plain strings or {text,status} dicts; return {text,status} dicts.
    Exactly one step is marked 'current' (the first non-done one) if any remain open."""
    norm: list[dict] = []
    for s in steps:
        if isinstance(s, str):
            norm.append({"text": s.strip(), "status": "open"})
        elif isinstance(s, dict) and s.get("text"):
            st = s.get("status", "open")
            norm.append({"text": str(s["text"]).strip(),
                         "status": st if st in _STATUSES else "open"})
    seen_current = False
    for s in norm:
        if s["status"] == "done":
            continue
        if not seen_current:
            s["status"] = "current"
            seen_current = True
        else:
            s["status"] = "open"
    return norm


def _row_to_dict(record) -> dict:
    data = dict(record)
    data["steps"] = json.loads(data["steps"]) if data.get("steps") else []
    data["guardrails"] = data.get("guardrails") or []
    data["notes"] = data.get("notes") or []
    data["sessions"] = data.get("sessions") or []
    data["project"] = data.get("project") or ""
    data["lane"] = data.get("lane") or ""
    data["label"] = data.get("label") or ""
    return data


_RETURN = ("RETURN f.project AS project, f.lane AS lane, f.label AS label, f.goal AS goal, "
           "f.steps AS steps, f.guardrails AS guardrails, f.done_when AS done_when, "
           "f.notes AS notes, f.sessions AS sessions, f.updated AS updated, "
           "f.last_seen AS last_seen")


def lane_for_session(session: Session, account: AuthedAccount, project: str, token: str) -> str | None:
    """The lane this session token is bound to, or None if it has none yet."""
    if not token:
        return None
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc, project: $project})
        WHERE $tok IN coalesce(f.sessions, [])
        RETURN f.lane AS lane LIMIT 1
        """,
        acc=account.uid, project=project or "", tok=token,
    ).single()
    return record["lane"] if record else None


def resolve_lane(
    session: Session, account: AuthedAccount, project: str = "",
    session_id: str = "", name: str = "",
) -> str | None:
    """Which lane does this caller mean? An explicit name wins; otherwise the lane bound to its
    session token; otherwise None (caller has no lane of its own -> the project-wide focus)."""
    if name:
        return _lane_slug(name)
    return lane_for_session(session, account, project, session_token(session_id))


def set_focus(
    session: Session, account: AuthedAccount, goal: str,
    steps: list, guardrails: list[str] | None, done_when: str = "", project: str = "",
    session_id: str = "", name: str = "", lane: str | None = None,
) -> dict:
    """Create/replace the focus for the caller's lane. With a session_id and no name, the session
    gets (or keeps) its OWN lane — parallel sessions in one project never overwrite each other.
    With a name, the session joins that named lane (creating it if needed)."""
    token = session_token(session_id)
    if lane is None:
        lane = resolve_lane(session, account, project, session_id, name)
        if lane is None:
            lane = f"s-{token}" if token else ""
    steps_norm = _normalize_steps(steps or [])
    session.run(
        """
        MERGE (f:HiveFocus {account_uid: $acc, project: $project, lane: $lane})
        ON CREATE SET f.uid = randomUUID(), f.org_uid = $org, f.created = timestamp(),
                      f.sessions = []
        SET f.goal = $goal, f.steps = $steps, f.guardrails = $guardrails,
            f.done_when = $done_when, f.notes = coalesce(f.notes, []),
            f.label = CASE WHEN $label <> '' THEN $label ELSE coalesce(f.label, '') END,
            f.sessions = CASE
                WHEN $tok = '' OR $tok IN coalesce(f.sessions, []) THEN coalesce(f.sessions, [])
                ELSE coalesce(f.sessions, []) + $tok END,
            f.updated = timestamp(), f.last_seen = timestamp()
        """,
        acc=account.uid, org=account.org_uid, project=project or "", lane=lane,
        goal=goal.strip(), steps=json.dumps(steps_norm, ensure_ascii=False),
        guardrails=[g.strip() for g in (guardrails or []) if g and g.strip()],
        done_when=done_when.strip(), label=(name or "").strip(), tok=token,
    )
    return get_focus(session, account, project, lane=lane)


def get_focus(
    session: Session, account: AuthedAccount, project: str = "",
    session_id: str = "", name: str = "", lane: str | None = None,
) -> dict | None:
    """The focus for the caller's lane. A session with no lane of its own falls back to the
    project-wide focus (lane ""), so clients that send no session id behave exactly as before."""
    if lane is None:
        lane = resolve_lane(session, account, project, session_id, name)
        if lane is None:
            lane = ""
    record = session.run(
        f"MATCH (f:HiveFocus {{account_uid: $acc, project: $project, lane: $lane}}) {_RETURN}",
        acc=account.uid, project=project or "", lane=lane,
    ).single()
    return _row_to_dict(record) if record else None


def list_for(session: Session, account: AuthedAccount, project: str | None = None) -> list[dict]:
    """All active foci (lanes) for this account — across projects, or within one project."""
    result = session.run(
        f"""
        MATCH (f:HiveFocus {{account_uid: $acc}})
        WHERE $project IS NULL OR f.project = $project
        {_RETURN} ORDER BY f.updated DESC
        """,
        acc=account.uid, project=project,
    )
    return [_row_to_dict(r) for r in result]


def touch(session: Session, account: AuthedAccount, project: str, lane: str) -> None:
    """Mark a lane as still alive (called on every recall) so stale lanes can be pruned."""
    session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc, project: $project, lane: $lane})
        SET f.last_seen = timestamp()
        """,
        acc=account.uid, project=project or "", lane=lane,
    )


def bind_session(
    session: Session, account: AuthedAccount, project: str, lane: str, session_id: str,
) -> bool:
    """Attach a session token to an existing lane, so its recall resolves to that focus."""
    token = session_token(session_id)
    if not token:
        return False
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc, project: $project, lane: $lane})
        SET f.sessions = CASE WHEN $tok IN coalesce(f.sessions, [])
            THEN f.sessions ELSE coalesce(f.sessions, []) + $tok END,
            f.last_seen = timestamp()
        RETURN f.uid AS uid
        """,
        acc=account.uid, project=project or "", lane=lane, tok=token,
    ).single()
    return record is not None


def prune_stale(session: Session, account: AuthedAccount, days: int = STALE_LANE_DAYS) -> int:
    """Delete session lanes nobody has recalled for `days` — a session that ended (or was
    /cleared) leaves its lane behind. The project-wide focus (lane "") is never pruned."""
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc})
        WHERE f.lane <> '' AND coalesce(f.last_seen, f.updated) < timestamp() - $ms
        WITH collect(f) AS stale
        FOREACH (f IN stale | DETACH DELETE f)
        RETURN size(stale) AS n
        """,
        acc=account.uid, ms=days * 86_400_000,
    ).single()
    return record["n"] if record else 0


def advance_focus(
    session: Session, account: AuthedAccount,
    completed_step: str | int | None = None, note: str | None = None, project: str = "",
    session_id: str = "", name: str = "", lane: str | None = None,
) -> dict | None:
    """Mark a step done (by 1-based number or matching text) and promote the next open step
    to 'current'; optionally append a short progress note."""
    focus = get_focus(session, account, project, session_id=session_id, name=name, lane=lane)
    if focus is None:
        return None
    lane = focus["lane"]
    steps = focus["steps"]

    if completed_step is not None and steps:
        idx = None
        if isinstance(completed_step, int):
            if 1 <= completed_step <= len(steps):
                idx = completed_step - 1
        else:
            want = str(completed_step).strip().lower()
            for i, s in enumerate(steps):
                if s["text"].strip().lower() == want or want in s["text"].strip().lower():
                    idx = i
                    break
        if idx is not None:
            steps[idx]["status"] = "done"
        steps = _normalize_steps(steps)

    notes = focus["notes"]
    if note and note.strip():
        notes = (notes + [note.strip()])[-5:]

    session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc, project: $project, lane: $lane})
        SET f.steps = $steps, f.notes = $notes, f.updated = timestamp(),
            f.last_seen = timestamp()
        """,
        acc=account.uid, project=project or "", lane=lane,
        steps=json.dumps(steps, ensure_ascii=False), notes=notes,
    )
    return get_focus(session, account, project, lane=lane)


def clear_focus(
    session: Session, account: AuthedAccount, project: str = "",
    session_id: str = "", name: str = "", lane: str | None = None,
    all_lanes: bool = False,
) -> int:
    """Clear the caller's lane — or, with all_lanes, every lane in this project. Returns how
    many foci were removed."""
    if all_lanes:
        record = session.run(
            """
            MATCH (f:HiveFocus {account_uid: $acc, project: $project})
            WITH collect(f) AS foci
            FOREACH (f IN foci | DETACH DELETE f)
            RETURN size(foci) AS n
            """,
            acc=account.uid, project=project or "",
        ).single()
        return record["n"] if record else 0

    if lane is None:
        lane = resolve_lane(session, account, project, session_id, name)
        if lane is None:
            lane = ""
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc, project: $project, lane: $lane})
        WITH f, f.uid AS uid
        DETACH DELETE f
        RETURN uid
        """,
        acc=account.uid, project=project or "", lane=lane,
    ).single()
    return 1 if record is not None else 0
