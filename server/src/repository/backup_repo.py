from __future__ import annotations

from collections import defaultdict

from neo4j import Session

from src.repository.graph_repo import KNOWLEDGE_TYPES

# Full backup/restore of an org's knowledge graph: every :Knowledge node (all properties incl.
# tags + embedding), the CONTAINS/RELATES edges between them, and the attachments (bytes). Not
# tenancy/tokens/secrets — those are operator state, not knowledge.

_REL_TYPES = ("CONTAINS", "RELATES")


def export_all(session: Session, org_uid: str) -> dict:
    nodes = []
    for r in session.run("MATCH (n:Knowledge {org_uid: $o}) RETURN n, labels(n) AS labels", o=org_uid):
        d = dict(r["n"])
        d["_labels"] = [l for l in r["labels"] if l != "Knowledge"]
        nodes.append(d)
    rels = [dict(r) for r in session.run(
        "MATCH (a:Knowledge {org_uid: $o})-[r:CONTAINS|RELATES]->(b:Knowledge {org_uid: $o}) "
        "RETURN a.uid AS a, b.uid AS b, type(r) AS t", o=org_uid)]
    atts = [dict(r["x"]) for r in session.run(
        "MATCH (:Knowledge {org_uid: $o})-[:HAS_ATTACHMENT]->(x:Attachment) RETURN x", o=org_uid)]
    return {"nodes": nodes, "relationships": rels, "attachments": atts}


def wipe(session: Session, org_uid: str) -> None:
    """Remove all of an org's knowledge, its attachments and chores (for a replace-restore).
    Leaves the org/accounts/tokens/secrets intact."""
    session.run("MATCH (:Knowledge {org_uid: $o})-[:HAS_ATTACHMENT]->(a:Attachment) DETACH DELETE a", o=org_uid)
    session.run("MATCH (c:Chore)-[:ABOUT]->(:Knowledge {org_uid: $o}) DETACH DELETE c", o=org_uid)
    session.run("MATCH (n:Knowledge {org_uid: $o}) DETACH DELETE n", o=org_uid)


def import_all(session: Session, org_uid: str, data: dict) -> dict:
    """Upsert nodes (MERGE on uid), their relationships and attachments into `org_uid`.
    Idempotent — re-importing the same dump is a no-op."""
    by_label: dict[str, list] = defaultdict(list)
    for n in data.get("nodes", []):
        n = dict(n)
        labels = n.pop("_labels", None) or []
        label = next((l for l in labels if l in KNOWLEDGE_TYPES.values()), "Memory")
        n["org_uid"] = org_uid   # restore into THIS org
        by_label[label].append(n)
    node_count = 0
    for label, ns in by_label.items():   # label from a fixed allowlist → safe to interpolate
        session.run(f"UNWIND $ns AS n MERGE (k:Knowledge:{label} {{uid: n.uid}}) SET k = n", ns=ns)
        node_count += len(ns)

    for t in _REL_TYPES:
        rs = [r for r in data.get("relationships", []) if r.get("t") == t]
        if rs:
            session.run(
                f"UNWIND $rs AS r MATCH (a:Knowledge {{uid: r.a, org_uid: $o}}), "
                f"(b:Knowledge {{uid: r.b, org_uid: $o}}) MERGE (a)-[:{t}]->(b)",
                rs=rs, o=org_uid)

    atts = [dict(a, org_uid=org_uid) for a in data.get("attachments", [])]
    if atts:
        session.run(
            "UNWIND $atts AS x MATCH (n:Knowledge {uid: x.node_uid, org_uid: $o}) "
            "MERGE (a:Attachment {uid: x.uid}) SET a = x MERGE (n)-[:HAS_ATTACHMENT]->(a)",
            atts=atts, o=org_uid)

    return {"nodes": node_count, "relationships": len(data.get("relationships", [])),
            "attachments": len(atts)}
