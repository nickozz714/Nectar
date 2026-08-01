from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session

from collections import Counter

from pydantic import BaseModel

from src.authentication.deps import AuthedAccount, has_role, require_account
from src.components.db import get_graph
from src.repository import audit_repo, governance_repo, graph_repo
from src.models.core import ChoreDecision
from src.services import curation_service, governance_service, memory_service, search_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/me")
def me(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "name": account.name,
        "person": graph_repo.account_info(session, account.uid).get("person"),
        "role": account.role,
        "org_uid": account.org_uid,
        "team_uid": account.team_uid,
        "can_maintain": has_role(account, "maintainer"),
        "can_review": has_role(account, "org_admin"),
        "can_resolve": has_role(account, "member"),   # any Swarm member may pick up ready Pollen
        "ready_chores": governance_repo.ready_count(session, account),
    }


@router.get("/topics")
def topics(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "topics": graph_repo.list_topics(session, account),
        "edges": graph_repo.topic_edges(session, account),
    }


@router.get("/search")
def search(
    q: str,
    tags: str = "",
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    # Browsing in the GUI should not rejuvenate memories — only actual use does.
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    results = search_service.search(session, account, q, limit=12, touch=False, tags=tag_list)
    return [
        {"uid": n["uid"], "title": n["title"], "type": n["type"],
         "scope": n.get("scope"), "topics": n.get("topics", []), "tags": n.get("tags", [])}
        for n in results
    ]


class TopicCreate(BaseModel):
    title: str
    parent_topic: str = ""


class NodeMove(BaseModel):
    to_topic: str
    keep_others: bool = False


class TopicMerge(BaseModel):
    from_topic: str
    into_topic: str


class TagEdit(BaseModel):
    add: list[str] = []
    remove: list[str] = []
    replace: list[str] | None = None


class RememberBody(BaseModel):
    type: str = "memory"
    title: str
    content: str
    parent_topics: list[str] = []
    tags: list[str] = []
    scope: str = "team"
    parent_node: str = ""
    force: bool = False


@router.post("/remember")
def remember(
    body: RememberBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Create a knowledge node from the GUI/HTTP (same write-gate as the MCP hive_remember)."""
    try:
        return memory_service.remember(
            session, account, body.type, body.title, body.content, body.parent_topics,
            body.scope, "gui", body.force, body.tags, body.parent_node,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ImportanceBody(BaseModel):
    uid: str
    value: float   # 0..1, 0.5 = neutral


@router.post("/importance")
def set_importance(
    body: ImportanceBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Pin a memory's importance (0..1) so recall ranks it higher/lower. Maintainer."""
    from src.authentication.deps import assert_role
    try:
        assert_role(account, "maintainer", "Setting importance")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not graph_repo.set_importance(session, account.org_uid, body.uid, body.value):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"uid": body.uid, "importance": max(0.0, min(1.0, body.value))}


class DecayBody(BaseModel):
    uid: str
    half_life_days: float | None = None   # None = use the global default


@router.post("/decay")
def set_decay(
    body: DecayBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Override a memory's decay half-life in days (fast for volatile knowledge). Maintainer."""
    from src.authentication.deps import assert_role
    try:
        assert_role(account, "maintainer", "Setting decay")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not graph_repo.set_half_life(session, account.org_uid, body.uid, body.half_life_days):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"uid": body.uid, "half_life_days": body.half_life_days}


class FeedbackBody(BaseModel):
    node_uid: str
    helped: bool


@router.post("/feedback")
def feedback(
    body: FeedbackBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """An agent reports whether a recalled memory actually helped — the causal 'Memory Worth'
    signal that makes decay outcome-based. Any member."""
    res = graph_repo.record_feedback(session, account.org_uid, body.node_uid, body.helped)
    if res is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return res


class LifecycleBody(BaseModel):
    uid: str
    state: str   # captured | validated | mature | deprecated


@router.post("/lifecycle")
def set_lifecycle(
    body: LifecycleBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Set a memory's Bloom lifecycle (captured→validated→mature, or deprecated). Maintainer."""
    from src.authentication.deps import assert_role
    try:
        assert_role(account, "maintainer", "Setting lifecycle")
        ok = graph_repo.set_lifecycle(session, account.org_uid, body.uid, body.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"uid": body.uid, "lifecycle": body.state}


class SupersedeBody(BaseModel):
    old_uid: str
    new_uid: str


@router.post("/supersede")
def supersede(
    body: SupersedeBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Record that `new_uid` supersedes `old_uid` (a newer fact replaces an older one). The old
    node stays findable but recall ranks it far below the current truth. Maintainer role."""
    from src.authentication.deps import assert_role
    try:
        assert_role(account, "maintainer", "Superseding a memory")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    result = graph_repo.supersede(session, account, body.old_uid, body.new_uid)
    if not result:
        raise HTTPException(status_code=404, detail="One of the nodes was not found or not visible")
    return result


class RelateBody(BaseModel):
    parent_uid: str
    child_uid: str
    relation: str = "contains"   # contains (hierarchy) or relates (cross-link)


@router.post("/relate")
def relate(
    body: RelateBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Link two nodes: contains (parent→child hierarchy) or relates (cross-reference). Lets
    you build parent→child→child chains. Maintainer role; cycle-checked for contains."""
    from src.authentication.deps import assert_role
    assert_role(account, "maintainer", "Linking nodes")
    try:
        if not graph_repo.link(session, account, body.parent_uid, body.child_uid, body.relation):
            raise HTTPException(status_code=404, detail="One of the nodes was not found")
        return {"linked": True, "relation": body.relation}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/unlink")
def unlink(
    body: RelateBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Remove a specific parent→child link (keeps other parents/relations). Maintainer role."""
    from src.authentication.deps import assert_role
    assert_role(account, "maintainer", "Unlinking nodes")
    return {"removed": graph_repo.unlink(session, account.org_uid, body.parent_uid, body.child_uid)}


@router.post("/topics")
def create_topic(
    body: TopicCreate,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.create_topic(session, account, body.title, body.parent_topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/node/{uid}/move")
def move_node(
    uid: str,
    body: NodeMove,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.move_node(session, account, uid, body.to_topic, body.keep_others)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/topics/merge")
def merge_topics(
    body: TopicMerge,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.merge_topics(session, account, body.from_topic, body.into_topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/nodes-brief")
def nodes_brief(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """All non-topic nodes (uid, title, type, topics, tags) — for bulk curation."""
    return curation_service.list_nodes_brief(session, account)


class BulkTags(BaseModel):
    items: list[dict]  # [{uid, tags}]


@router.post("/tags/bulk")
def bulk_tags(
    body: BulkTags,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.bulk_set_tags(session, account, body.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reclassify-sensitivity")
def reclassify_sensitivity(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.reclassify_sensitivity(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reindex")
def reindex(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Recompute contextual embeddings for this org's knowledge (org_admin). Run after
    enabling contextual embeddings or switching the embedding model."""
    from src.authentication.deps import assert_role
    from src.services import reindex_service
    try:
        assert_role(account, "org_admin", "Reindexing embeddings")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return reindex_service.reembed(session, account.org_uid)


class ThinkResolveBody(BaseModel):
    pollen_uid: str
    decision: str   # ADD | UPDATE | DELETE | NOOP
    merged_title: str = ""
    merged_content: str = ""
    note: str = ""


@router.post("/think/resolve")
def resolve_think(
    body: ThinkResolveBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Resolve an op_route think-Pollen (swarm decides ADD/UPDATE/DELETE/NOOP for a near-duplicate).
    UPDATE/DELETE require a different account than the one who wrote the new memory."""
    try:
        return governance_service.resolve_think(
            session, account, body.pollen_uid, body.decision,
            body.merged_title, body.merged_content, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/analytics")
def analytics(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Insight into the mind: totals by lifecycle, most-used memories, never-used (archive
    candidates), and knowledge gaps (repeated empty recalls). Any member."""
    return graph_repo.analytics(session, account.org_uid)


@router.post("/topic-summaries")
def topic_summaries(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """(Re)build the deterministic per-topic summaries. Maintainer."""
    try:
        return curation_service.build_topic_summaries(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/train-ranker")
def train_ranker(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Train the learning-to-rank model from accumulated recall feedback. Maintainer."""
    from src.services import ltr_service
    try:
        return ltr_service.train(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/linkpred-scan")
def linkpred_scan(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Propose RELATES links between probably-related memories as suggestion-Pollen. Maintainer."""
    try:
        return curation_service.link_prediction_scan(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/pagerank-scan")
def pagerank_scan(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Recompute structural importance (PageRank) over the knowledge graph. Maintainer."""
    try:
        return curation_service.pagerank_scan(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/staleness-scan")
def staleness_scan(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Surface stale-but-relied-upon knowledge as review Pollen ('still correct?'). Maintainer."""
    try:
        return curation_service.staleness_scan(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tidy-scan")
def tidy_scan(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Housekeeping scan: file loose knowledge under the nearest topic by opening (safe,
    non-destructive) promotion chores. Part of the recurring tidy/re-organise loop."""
    try:
        return curation_service.tidy_scan(session, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/node/{uid}/tags")
def set_tags(
    uid: str,
    body: TagEdit,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    try:
        return curation_service.set_tags(session, account, uid, body.add, body.remove, body.replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/node/{uid}")
def node(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    data = graph_repo.get_node(session, account, uid)
    if data is None:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    files = graph_repo.node_files(session, account, uid)
    if files:
        data["files"] = files
    return data


@router.get("/neighbors/{uid}")
def node_neighbors(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    data = graph_repo.neighbors(session, account, uid)
    if not data:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    return data


@router.get("/chores")
def chores(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    return {
        "ready": governance_repo.ready_count(session, account),
        "chores": governance_repo.open_chores(session, account, limit=25),
        "resolved": governance_repo.resolved_chores(session, account, limit=25),
    }


@router.get("/lineage/{uid}")
def lineage(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Purview-style lineage for one knowledge node: who (person) via which account and
    model created it, and every governance event that touched it since."""
    node = graph_repo.get_node(session, account, uid)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found or not visible")
    creator = graph_repo.account_info(session, node.get("created_by"))
    return {
        "uid": uid,
        "title": node.get("title"),
        "created_at": node.get("created"),
        "created_by_account": creator.get("name"),
        "created_by_person": creator.get("person"),
        "created_by_model": node.get("created_by_model") or "onbekend",
        "sensitivity": node.get("sensitivity", "intern"),
        "scope": node.get("scope"),
        "use_count": node.get("use_count", 0),
        "events": audit_repo.events_for_target(session, account.org_uid, uid),
    }


@router.delete("/node/{uid}")
def delete_node(
    uid: str,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """org_admin: permanently delete a knowledge node (escape hatch from consensus)."""
    try:
        return governance_service.admin_delete(session, account, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/governance")
def governance(
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Purview-style transparency: what lives in the mind, how it is classified, who/what
    wrote it, and where governance work stands. Visible to every member — the hive must
    be open about itself."""
    rows = graph_repo.governance_rows(session, account)
    return {
        "nodes_total": len(rows),
        "by_scope": dict(Counter(r["scope"] for r in rows)),
        "by_type": dict(Counter(r["type"] for r in rows)),
        "by_sensitivity": dict(Counter(r["sensitivity"] for r in rows)),
        "by_model": dict(Counter(r["model"] or "onbekend" for r in rows)),
        "sensitive_nodes": [
            {"uid": r["uid"], "title": r["title"], "type": r["type"]}
            for r in rows if r["sensitivity"] == "gevoelig"
        ],
        "chores": graph_repo.chore_status_counts(session, account.org_uid),
    }


@router.get("/audit")
def audit(
    limit: int = 100,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Append-only audit trail (org_admin): every write, mutation and secret access."""
    if not has_role(account, "org_admin"):
        raise HTTPException(status_code=403, detail="org_admin role required")
    return audit_repo.recent(session, account.org_uid, min(limit, 500))


class SuggestBody(BaseModel):
    kind: str
    node_uid: str
    payload: dict = {}
    rationale: str = ""
    model_name: str = ""


@router.post("/suggest")
def suggest(
    body: SuggestBody,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """File a mutation suggestion from the GUI (same consensus path as the MCP tool)."""
    try:
        return governance_service.suggest(
            session, account, body.kind, body.node_uid, body.payload,
            body.rationale, body.model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chores/{chore_uid}/resolve")
def resolve_chore(
    chore_uid: str,
    body: ChoreDecision,
    action: str = "apply",
    direct: bool = False,
    account: AuthedAccount = Depends(require_account),
    session: Session = Depends(get_graph),
):
    """Resolve a chore. `direct=true` is the org_admin bypass for chores that never reached
    consensus ('open'); otherwise a maintainer resolves a 'ready' chore the normal way."""
    try:
        if direct:
            return governance_service.admin_resolve(session, account, chore_uid, action, body.note)
        return governance_service.resolve(session, account, chore_uid, action, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
