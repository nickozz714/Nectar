from __future__ import annotations

import json

from neo4j import Session

from src.authentication.deps import AuthedAccount

# The ACTIVE FOCUS: one living task per account that the recall hook re-injects on every
# prompt, so a long session doesn't drift or lose the plan after compaction. Its own label
# (:HiveFocus) so it never leaks into shared recall/search — it is steering state, not
# knowledge. Steps are stored as a JSON string (Neo4j has no list-of-maps); guardrails are
# a native string list.

_STATUSES = ("done", "current", "open")


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
    # ensure a single 'current': first not-done becomes current, others open
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


def set_focus(
    session: Session, account: AuthedAccount, goal: str,
    steps: list, guardrails: list[str] | None, done_when: str = "",
) -> dict:
    steps_norm = _normalize_steps(steps or [])
    record = session.run(
        """
        MERGE (f:HiveFocus {account_uid: $acc})
        ON CREATE SET f.uid = randomUUID(), f.org_uid = $org, f.created = timestamp()
        SET f.goal = $goal, f.steps = $steps, f.guardrails = $guardrails,
            f.done_when = $done_when, f.notes = coalesce(f.notes, []), f.updated = timestamp()
        RETURN f.uid AS uid
        """,
        acc=account.uid, org=account.org_uid, goal=goal.strip(),
        steps=json.dumps(steps_norm, ensure_ascii=False),
        guardrails=[g.strip() for g in (guardrails or []) if g and g.strip()],
        done_when=done_when.strip(),
    ).single()
    return get_focus(session, account) or {"uid": record["uid"]}


def get_focus(session: Session, account: AuthedAccount) -> dict | None:
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc})
        RETURN f.goal AS goal, f.steps AS steps, f.guardrails AS guardrails,
               f.done_when AS done_when, f.notes AS notes, f.updated AS updated
        """,
        acc=account.uid,
    ).single()
    if record is None:
        return None
    data = dict(record)
    data["steps"] = json.loads(data["steps"]) if data.get("steps") else []
    data["guardrails"] = data.get("guardrails") or []
    data["notes"] = data.get("notes") or []
    return data


def advance_focus(
    session: Session, account: AuthedAccount,
    completed_step: str | int | None = None, note: str | None = None,
) -> dict | None:
    """Mark a step done (by 1-based number or by matching text) and promote the next open
    step to 'current'; optionally append a short progress note."""
    focus = get_focus(session, account)
    if focus is None:
        return None
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
        steps = _normalize_steps(steps)  # re-elect the current step

    notes = focus["notes"]
    if note and note.strip():
        notes = notes + [note.strip()]
        notes = notes[-5:]  # keep the last few

    session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc})
        SET f.steps = $steps, f.notes = $notes, f.updated = timestamp()
        """,
        acc=account.uid,
        steps=json.dumps(steps, ensure_ascii=False),
        notes=notes,
    )
    return get_focus(session, account)


def clear_focus(session: Session, account: AuthedAccount) -> bool:
    record = session.run(
        """
        MATCH (f:HiveFocus {account_uid: $acc})
        WITH f, f.uid AS uid
        DETACH DELETE f
        RETURN uid
        """,
        acc=account.uid,
    ).single()
    return record is not None
