from __future__ import annotations

import json

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role, has_role
from src.components.config import get_settings
from src.repository import audit_repo, governance_repo, graph_repo, tenancy_repo
from src.components.embeddings import embed


def suggest(
    session: Session,
    account: AuthedAccount,
    chore_type: str,
    node_uid: str,
    payload: dict,
    rationale: str,
    model_name: str,
) -> dict:
    if chore_type not in governance_repo.POLLEN_TYPES:
        raise ValueError(f"kind must be one of: {', '.join(sorted(governance_repo.POLLEN_TYPES))}")
    result = governance_repo.suggest(
        session, account, chore_type, node_uid, payload, rationale, model_name,
        threshold=tenancy_repo.get_consensus_threshold(
            session, account.org_uid, get_settings().CONSENSUS_THRESHOLD),
    )
    if result is None:
        raise ValueError("Node not found or not visible to this account")
    audit_repo.log(session, account.org_uid, account.uid, "suggest", node_uid,
                   {"kind": chore_type, "chore": result["uid"]})
    return result


def resolve(
    session: Session, account: AuthedAccount, chore_uid: str, action: str, note: str
) -> dict:
    """A bee resolves a 'ready' chore — maintainer role required, so upkeep is
    delegated deliberately instead of open to everyone. scope_widening never passes
    through here — that is the one mutation reserved for a human reviewer."""
    assert_role(account, "member", "Resolving Pollen")   # any Swarm member may pick up ready Pollen
    chore = governance_repo.get_chore(session, account.org_uid, chore_uid)
    if chore is None:
        raise ValueError("Chore not found")
    if chore["status"] != "ready":
        raise ValueError(f"Chore is '{chore['status']}', only 'ready' chores can be resolved by the swarm")
    if chore["type"] == "scope_widening":
        raise ValueError("scope_widening is decided by a human via the admin review queue")
    if action == "reject":
        governance_repo.close_chore(session, chore_uid, "rejected", account.uid, note)
        return {"status": "rejected"}
    if action != "apply":
        raise ValueError("action must be apply or reject")

    payload = json.loads(chore["payload"] or "{}")
    applied = _apply(session, account, chore, payload)
    governance_repo.close_chore(session, chore_uid, "resolved", account.uid, note or applied)
    audit_repo.log(session, account.org_uid, account.uid, "resolve_chore", chore_uid,
                   {"kind": chore["type"], "node": chore["node_uid"], "result": applied})
    return {"status": "resolved", "applied": applied}


def admin_resolve(
    session: Session, account: AuthedAccount, chore_uid: str, action: str, note: str
) -> dict:
    """org_admin escape hatch: resolve a chore that has NOT reached consensus ('open') or is
    'ready', directly — for small/solo orgs where the 2-vote threshold never triggers.
    Audited as a bypass. scope_widening still goes through the human review queue."""
    assert_role(account, "org_admin", "Directly resolving chores")
    chore = governance_repo.get_chore(session, account.org_uid, chore_uid)
    if chore is None:
        raise ValueError("Chore not found")
    if chore["status"] not in ("open", "ready"):
        raise ValueError(f"Chore is '{chore['status']}' — already handled")
    if chore["type"] == "scope_widening":
        raise ValueError("scope_widening is decided by a human via the admin review queue")
    if action == "reject":
        governance_repo.close_chore(session, chore_uid, "rejected", account.uid, note or "org_admin afgewezen")
        audit_repo.log(session, account.org_uid, account.uid, "admin_resolve_chore", chore_uid,
                       {"kind": chore["type"], "action": "reject", "bypass": "consensus"})
        return {"status": "rejected"}
    if action != "apply":
        raise ValueError("action must be apply or reject")

    payload = json.loads(chore["payload"] or "{}")
    applied = _apply(session, account, chore, payload)
    governance_repo.close_chore(session, chore_uid, "resolved", account.uid, note or applied)
    audit_repo.log(session, account.org_uid, account.uid, "admin_resolve_chore", chore_uid,
                   {"kind": chore["type"], "node": chore["node_uid"], "result": applied,
                    "bypass": "consensus"})
    return {"status": "resolved", "applied": applied}


def _apply(session: Session, account: AuthedAccount, chore: dict, payload: dict) -> str:
    kind, node_uid = chore["type"], chore["node_uid"]
    if kind == "edit":
        content = payload.get("content")
        embedding = embed(f"{payload.get('title', '')}\n{content}") if content else None
        graph_repo.update_node(session, node_uid, payload, embedding)
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")  # reviewed edit
        return "node updated"
    if kind == "invalidate":
        graph_repo.archive_node(session, node_uid)
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "deprecated")
        return "node archived (never hard-deleted)"
    if kind == "promotion":
        target = payload.get("target_topic")
        if not target:
            raise ValueError("promotion payload needs target_topic")
        topic = graph_repo.find_or_create_topic(session, account.org_uid, target, account.uid)
        graph_repo.link(session, account, topic["uid"], node_uid, "contains")
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")  # swarm reviewed it
        return f"re-linked under '{topic['title']}' (origin links and scope kept)"
    if kind == "dedup_merge":
        duplicate = payload.get("duplicate_uid")
        if not duplicate:
            raise ValueError("dedup_merge payload needs duplicate_uid")
        graph_repo.archive_node(session, duplicate)
        graph_repo.set_lifecycle(session, account.org_uid, duplicate, "deprecated")
        return "duplicate archived"
    if kind == "relate_suggest":
        other = payload.get("other_uid")
        if not other:
            raise ValueError("relate_suggest payload needs other_uid")
        graph_repo.link(session, account, node_uid, other, "relates")
        return "linked as related"
    if kind == "stale_review":
        # "yes, still correct" — refresh it (resets the decay clock) and confirm it as validated.
        graph_repo.touch_nodes(session, [node_uid])
        graph_repo.set_lifecycle(session, account.org_uid, node_uid, "validated")
        return "reviewed — confirmed current"
    raise ValueError(f"Unknown chore type {kind}")


def admin_delete(session: Session, account: AuthedAccount, uid: str) -> dict:
    """org_admin escape hatch: permanently delete a knowledge node. Bypasses the
    consensus gate on purpose (humans prune), and is audited."""
    assert_role(account, "org_admin", "Deleting memories")
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    graph_repo.hard_delete(session, account.org_uid, uid)
    audit_repo.log(session, account.org_uid, account.uid, "delete", uid,
                   {"title": node.get("title"), "type": node.get("type")})
    return {"deleted": True, "uid": uid, "title": node.get("title")}


def set_system(session: Session, account: AuthedAccount, uid: str, on: bool) -> dict:
    """org_admin: mark a node as a SYSTEM memory (always injected into recall) or unmark it.
    Use for standing instructions like 'how to work with the Nectar'."""
    assert_role(account, "org_admin", "Setting system memories")
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise ValueError("Node not found or not visible")
    graph_repo.set_system(session, account.org_uid, uid, on)
    audit_repo.log(session, account.org_uid, account.uid, "set_system", uid, {"on": on})
    return {"uid": uid, "system": on, "title": node.get("title")}


def approve_scope_widening(
    session: Session, chore_uid: str, org_uid: str, note: str, reviewed_by: str = "human-admin"
) -> dict:
    """Human decision: widen a node's visibility (e.g. team -> org)."""
    chore = governance_repo.get_chore(session, org_uid, chore_uid)
    if chore is None or chore["status"] != "awaiting_human":
        raise ValueError("Chore not found or not awaiting human review")
    payload = json.loads(chore["payload"] or "{}")
    target_scope = payload.get("target_scope", "org")
    if target_scope not in ("org", "team"):
        raise ValueError("target_scope must be org or team")
    graph_repo.set_scope(session, chore["node_uid"], target_scope)
    governance_repo.close_chore(session, chore_uid, "resolved", reviewed_by, note)
    audit_repo.log(session, org_uid, None, "approve_scope_widening", chore["node_uid"],
                   {"chore": chore_uid, "target_scope": target_scope, "reviewed_by": reviewed_by})
    return {"status": "resolved", "node_uid": chore["node_uid"], "scope": target_scope}


def _cos(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


_POLLEN_VERB = {
    "promotion": "een node onder een beter topic hangen",
    "dedup_merge": "een duplicaat samenvoegen",
    "edit": "een voorgestelde tekstwijziging beoordelen",
    "invalidate": "verouderde kennis archiveren",
    "scope_widening": "een scope-verbreding beoordelen (mens)",
    "stale_review": "een oude-maar-veelgebruikte memory herbevestigen of bijwerken",
    "op_route": "beslissen hoe een bijna-duplicaat te verwerken (samenvoegen/behouden/schrappen)",
    "relate_suggest": "twee waarschijnlijk-gerelateerde memories aan elkaar koppelen (RELATES)",
    "contradiction_check": "beoordelen of twee memories elkaar tegenspreken (en supersession voorstellen)",
}


def pick_contextual_pollen(session: Session, account: AuthedAccount, query: str) -> dict | None:
    """Choose the single most relevant open/ready Pollen (chore) for what the agent is doing:
    rank candidates by embedding similarity between the agent's prompt and the chore's node,
    with a small boost for 'ready'. Returns the chore dict (or None if the hive has no Pollen)."""
    from src.components.embeddings import embed

    cands = governance_repo.candidate_pollen(
        session, account, limit=25, ttl_min=get_settings().CLAIM_TTL_MIN)
    if not cands:
        return None
    qv = embed(query) if query else None

    def score(c):
        sim = _cos(qv, c.get("embedding")) if qv else 0.0
        return sim + (0.15 if c["status"] == "ready" else 0.0)

    return max(cands, key=score)


def _excerpt(text: str | None, limit: int = 1200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def build_pollen_view(session: Session, account: AuthedAccount, chore: dict) -> dict:
    """Turn a raw Pollen (a type + a uid-laden payload) into a human-readable decision card: the
    actual memory text involved, a plain-language 'what approving does', a before/after for edits,
    and which resolve-route the UI should offer. Uids are carried only for the action buttons —
    never for display — so a human sees titles and text, not identifiers."""
    kind = chore["type"]
    try:
        payload = json.loads(chore.get("payload") or "{}")
    except (ValueError, TypeError):
        payload = {}
    node_uid = chore.get("node_uid")
    node_title = chore.get("node_title") or ""

    refs = [node_uid, payload.get("duplicate_uid"), payload.get("other_uid")]
    texts = governance_repo.nodes_text(session, account, [r for r in refs if r])

    def node_of(uid, label=None):
        t = texts.get(uid) or {}
        card = {"title": t.get("title", ""), "content": _excerpt(t.get("content"))}
        if label:
            card["label"] = label
        return card

    primary = node_of(node_uid) if node_uid else None
    view = {
        "route": "standard",            # standard | contradiction | op_route | human
        "headline": kind,
        "explain": "",
        "primary": primary,
        "compare": None,
        "proposed": None,
        "target_topic": None,
        "similarity": payload.get("similarity"),
        "refs": {"pollen": chore["uid"], "node": node_uid},
    }

    if kind == "edit":
        view["headline"] = "Wijziging aan een memory"
        view["explain"] = ("Keur je goed, dan wordt de inhoud van deze memory vervangen door de "
                           "voorgestelde tekst.")
        view["proposed"] = {"title": payload.get("title") or (primary["title"] if primary else ""),
                            "content": _excerpt(payload.get("content"))}
    elif kind == "invalidate":
        view["headline"] = "Memory archiveren"
        view["explain"] = ("Keur je goed, dan wordt deze memory gearchiveerd — weg uit recall, maar "
                           "blijft in de historie. Nooit hard verwijderd.")
        if payload.get("reason"):
            view["explain"] += f" Reden: {payload['reason']}"
    elif kind == "promotion":
        view["headline"] = "Memory onder een topic hangen"
        view["target_topic"] = payload.get("target_topic")
        view["explain"] = (f"Keur je goed, dan komt deze memory (ook) onder het topic "
                           f"'{payload.get('target_topic','')}'. Bestaande koppelingen en scope blijven.")
    elif kind == "dedup_merge":
        if primary:
            primary["label"] = "Blijft"
        view["compare"] = node_of(payload.get("duplicate_uid"), "Wordt gearchiveerd (dubbel)")
        view["headline"] = "Dubbele memory opruimen"
        view["explain"] = ("Twee memories zijn (bijna) identiek. Keur je goed, dan blijft de eerste "
                           "en wordt de tweede gearchiveerd.")
    elif kind == "relate_suggest":
        if primary:
            primary["label"] = "Deze memory"
        view["compare"] = node_of(payload.get("other_uid"), "Voorgestelde koppeling")
        view["headline"] = "Verband voorstellen"
        view["explain"] = ("Deze twee memories horen waarschijnlijk bij elkaar. Keur je goed, dan "
                           "worden ze als 'gerelateerd' gekoppeld — nooit samengevoegd.")
    elif kind == "stale_review":
        view["headline"] = "Klopt dit nog?"
        view["explain"] = ("Deze memory is oud maar wordt veel gebruikt. Toepassen = 'nog steeds "
                           "correct' (ververst 'm); afwijzen als 'ie niet meer klopt.")
    elif kind == "scope_widening":
        view["route"] = "human"
        view["headline"] = "Zichtbaarheid verbreden"
        view["explain"] = (f"Voorstel om deze memory breder zichtbaar te maken (→ "
                           f"{payload.get('target_scope','org')}). Dit besluit is voor een mens.")
    elif kind == "op_route":
        view["route"] = "op_route"
        if primary:
            primary["label"] = "Nieuwe memory"
        view["compare"] = node_of(payload.get("duplicate_uid"), "Bestaande memory die erop lijkt")
        view["headline"] = "Bijna-duplicaat: hoe verwerken?"
        view["merge_requested"] = bool(payload.get("merge_requested"))
        view["explain"] = ("Een nieuwe memory lijkt sterk op een bestaande. Kies wat er gebeurt: "
                           "allebei houden, de nieuwe laten winnen (de bestaande wordt gesuperseded), "
                           "de nieuwe schrappen, of laten staan. Samenvoegen zet je klaar als taak voor "
                           "de zwerm — die schrijft de gecombineerde tekst.")
    elif kind == "contradiction_check":
        view["route"] = "contradiction"
        view["primary"] = {"title": payload.get("a_title", ""),
                           "content": _excerpt(payload.get("a_content")), "label": "Memory A"}
        view["compare"] = {"title": payload.get("b_title", ""),
                           "content": _excerpt(payload.get("b_content")), "label": "Memory B"}
        view["headline"] = "Mogelijke tegenspraak"
        view["explain"] = ("Twee memories lijken sterk op elkaar. Spreken ze elkaar tegen? Zo ja, "
                           "kies welke de huidige waarheid is — de andere wordt gesuperseded "
                           "(blijft vindbaar, zakt weg). Zo nee: 'verenigbaar'.")
        view["refs"]["a"] = payload.get("a_uid")
        view["refs"]["b"] = payload.get("b_uid")
    return view


def render_pollen(pollen: dict) -> str:
    """One-line instruction that hands the agent a bit of Pollen to carry."""
    import json as _json
    what = _POLLEN_VERB.get(pollen["type"], pollen["type"])
    payload = {}
    try:
        payload = _json.loads(pollen.get("payload") or "{}")
    except (ValueError, TypeError):
        pass
    target = payload.get("target_topic")
    detail = f" → voorstel: onder '{target}'" if target else ""
    node = pollen.get("node_title") or ""
    node = node[:70] + "…" if len(node) > 70 else node
    if pollen["type"] == "contradiction_check":
        how = (f"Lees beide met `hive_get`, oordeel, en los op met "
               f"`hive_resolve_contradiction(\"{pollen['uid']}\", \"contradiction\"|\"compatible\", "
               f"current=…, outdated=…)`.")
    elif pollen["type"] == "op_route":
        how = (f"Beoordeel en los op met "
               f"`hive_resolve_think(\"{pollen['uid']}\", …)`.")
    else:
        how = (f"Beoordeel 'm op inhoud en los 'm op met `hive_chores()` → "
               f"`hive_resolve_chore(\"{pollen['uid']}\", \"apply\"|\"reject\")`.")
    return (f"🌼 **Pollen** — draag bij aan de Hive terwijl je hier toch bent: {what} "
            f"voor *{node}*{detail}. Past het bij je taak? {how}")


def resolve_think(
    session: Session, account: AuthedAccount, pollen_uid: str, decision: str,
    merged_title: str = "", merged_content: str = "", note: str = "",
) -> dict:
    """Resolve an op_route think-Pollen: a swarm agent decides how to reconcile a near-duplicate.
    SAFEGUARD (producer≠reviewer): the DESTRUCTIVE decisions (UPDATE/DELETE) may not be made by the
    account that WROTE the new memory — a different Swarm member must judge the merge. The result
    of an UPDATE enters lifecycle 'validated' (a peer confirmed it); the new node is archived."""
    assert_role(account, "member", "Resolving a think-Pollen")
    decision = (decision or "").strip().upper()
    if decision not in ("ADD", "UPDATE", "DELETE", "NOOP", "REPLACE"):
        raise ValueError("decision must be ADD, UPDATE, DELETE, NOOP or REPLACE")
    chore = governance_repo.get_chore(session, account.org_uid, pollen_uid)
    if chore is None or chore["type"] != "op_route":
        raise ValueError("op_route think-Pollen not found")
    if chore["status"] not in ("open", "ready"):
        raise ValueError(f"already handled ('{chore['status']}')")
    payload = json.loads(chore["payload"] or "{}")
    new_uid = chore["node_uid"]                 # the just-written (possibly duplicate) memory
    keep_uid = payload.get("duplicate_uid")     # the existing memory it resembles
    new_node = graph_repo.get_node(session, account, new_uid)
    if new_node is None:
        raise ValueError("the new memory no longer exists")

    # producer≠reviewer on the destructive decisions — but an org_admin (a human reviewer) may always
    # resolve, otherwise a human who happens to own the token would be locked out of their own GUI.
    if (decision in ("UPDATE", "DELETE", "REPLACE")
            and new_node.get("created_by") == account.uid
            and not has_role(account, "org_admin")):
        raise ValueError("producer≠reviewer: a DIFFERENT Swarm member must judge this — you wrote "
                         "the new memory. Ask another agent, or choose ADD/NOOP.")

    if decision in ("ADD", "NOOP"):
        result = "kept both — judged as distinct" if decision == "ADD" else "left as-is"
    elif decision == "DELETE":
        graph_repo.archive_node(session, new_uid)
        graph_repo.set_lifecycle(session, account.org_uid, new_uid, "deprecated")
        result = "new memory archived as a duplicate"
    elif decision == "REPLACE":     # the NEW memory becomes the truth; the existing one is superseded
        if not keep_uid:
            raise ValueError("REPLACE needs the existing memory it replaces")
        got = graph_repo.supersede(session, account, keep_uid, new_uid)  # old=keep_uid, new=new_uid
        if not got:
            raise ValueError("could not supersede — a node is not visible")
        result = "existing memory superseded by the new one (new wins, old stays findable)"
    else:  # UPDATE — merge into the kept node
        if not keep_uid or not merged_content.strip():
            raise ValueError("UPDATE needs the existing memory + merged_content")
        title = merged_title.strip() or graph_repo.get_node(session, account, keep_uid)["title"]
        embedding = embed(f"{title}\n{merged_content}")
        graph_repo.update_node(session, keep_uid, {"title": title, "content": merged_content}, embedding)
        graph_repo.set_lifecycle(session, account.org_uid, keep_uid, "validated")  # peer-confirmed merge
        graph_repo.archive_node(session, new_uid)
        graph_repo.set_lifecycle(session, account.org_uid, new_uid, "deprecated")
        result = "merged into the existing memory; new one archived"

    governance_repo.close_chore(session, pollen_uid, "resolved", account.uid, note or f"{decision}: {result}")
    audit_repo.log(session, account.org_uid, account.uid, "resolve_think", pollen_uid,
                   {"kind": "op_route", "decision": decision, "new": new_uid, "keep": keep_uid})
    return {"status": "resolved", "decision": decision, "result": result}


def request_merge(session: Session, account: AuthedAccount, pollen_uid: str, note: str = "") -> dict:
    """A human can't sensibly hand-type a merge in the GUI (it's a reasoning task). So instead of
    resolving, they FLAG the op_route Pollen as 'merge wanted'; it stays open for the Swarm, and a
    visiting agent performs the actual UPDATE-merge. The producer≠reviewer rule still applies when
    that agent resolves it."""
    assert_role(account, "member", "Requesting a merge")
    chore = governance_repo.get_chore(session, account.org_uid, pollen_uid)
    if chore is None or chore["type"] != "op_route":
        raise ValueError("op_route think-Pollen not found")
    if chore["status"] not in ("open", "ready"):
        raise ValueError(f"already handled ('{chore['status']}')")
    governance_repo.flag_pollen(session, account.org_uid, pollen_uid, "merge_requested", True)
    audit_repo.log(session, account.org_uid, account.uid, "request_merge", pollen_uid, {"kind": "op_route"})
    return {"status": "merge_requested"}


def resolve_contradiction(
    session: Session, account: AuthedAccount, pollen_uid: str, verdict: str,
    current_uid: str = "", outdated_uid: str = "", note: str = "",
) -> dict:
    """Resolve a contradiction-check think-Pollen: the swarm judged whether two similar memories
    conflict. 'compatible' → close. 'contradiction' → supersede the outdated one by the current one
    (the old fact stays findable but sinks; the current wins deterministically)."""
    assert_role(account, "member", "Resolving a contradiction-check")
    verdict = (verdict or "").strip().lower()
    chore = governance_repo.get_chore(session, account.org_uid, pollen_uid)
    if chore is None or chore["type"] != "contradiction_check":
        raise ValueError("contradiction-check think-Pollen not found")
    if chore["status"] not in ("open", "ready"):
        raise ValueError(f"already handled ('{chore['status']}')")
    payload = json.loads(chore["payload"] or "{}")
    pair = {payload.get("a_uid"), payload.get("b_uid")}
    if verdict == "compatible":
        result = "judged compatible — no conflict"
    elif verdict in ("contradiction", "contradict", "conflict"):
        if {current_uid, outdated_uid} != pair or current_uid == outdated_uid:
            raise ValueError("current and outdated must be the two memories in this pair")
        got = graph_repo.supersede(session, account, outdated_uid, current_uid)
        if not got:
            raise ValueError("could not supersede — one node not visible")
        result = "contradiction resolved — outdated superseded by current"
    else:
        raise ValueError("verdict must be 'contradiction' or 'compatible'")
    governance_repo.close_chore(session, pollen_uid, "resolved", account.uid, note or result)
    audit_repo.log(session, account.org_uid, account.uid, "resolve_contradiction", pollen_uid,
                   {"verdict": verdict, "current": current_uid, "outdated": outdated_uid})
    return {"status": "resolved", "verdict": verdict, "result": result}
