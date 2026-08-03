# Reaching Neo4j directly + Cypher cookbook

Nectar's data is a normal Neo4j 5 graph. You never *need* to touch Neo4j directly — the API/MCP and
the GUI cover day-to-day use — but for audits, ad-hoc analysis, or emergency fixes it's there.

> ⚠️ **The API is the source of truth for writes.** The write-gate, embeddings, audit trail and
> consensus rules all live in the app. Writing straight to Neo4j bypasses them: you can create nodes
> with no embedding (invisible to vector search), skip the audit log, or corrupt invariants. Treat
> direct Bolt access as **read-mostly**; for bulk changes prefer an idempotent startup migration in
> `components/db.py` (which runs inside the app on deploy).

## Ways in

### 1. Neo4j Browser (visual, read/query)
Exposed on **`:7474`** (HTTP) → connects over Bolt `:7687`. Open `http://<host>:7474`, connect with
`neo4j` / `NEO4J_PASSWORD`. **Never expose 7474/7687 to the public internet** — keep them on the LAN
or behind a VPN/tunnel.

### 2. cypher-shell (CLI, inside the container)
```bash
docker exec -it <nectar-container> cypher-shell -u neo4j -p "$NEO4J_PASSWORD"
```

### 3. Python driver (scripting)
```python
from neo4j import GraphDatabase
drv = GraphDatabase.driver("bolt://<host>:7687", auth=("neo4j", "…"))
with drv.session() as s:
    for r in s.run("MATCH (n:Knowledge) RETURN count(n) AS n"):
        print(r["n"])
```

### 4. Over a tunnel (recommended for remote)
Don't publish Bolt. Instead:
```bash
ssh -N -L 7687:localhost:7687 -L 7474:localhost:7474 user@host   # then use localhost
```

---

## Cypher cookbook (frequently used)

Replace `$org` with your org uid (find it with the first query). All knowledge queries should filter
by `org_uid` — the app always does.

### Orientation

```cypher
// orgs and their sizes
MATCH (o:Org) OPTIONAL MATCH (n:Knowledge {org_uid:o.uid})
RETURN o.uid, o.name, count(n) AS memories ORDER BY memories DESC;

// counts by label
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (:`'+label+'`) RETURN count(*) AS c',{}) YIELD value
RETURN label, value.c ORDER BY value.c DESC;   // (or count per label individually if no APOC)

// what indexes exist
SHOW INDEXES;
```

### Inventory & health

```cypher
// memories by type and lifecycle
MATCH (n:Knowledge {org_uid:$org}) WHERE n.type <> 'topic'
RETURN n.type AS type, coalesce(n.lifecycle,'?') AS bloom, count(*) AS c
ORDER BY c DESC;

// never-used memories (archive candidates)
MATCH (n:Knowledge {org_uid:$org}) WHERE coalesce(n.use_count,0)=0 AND coalesce(n.archived,false)=false
RETURN n.title, n.type ORDER BY n.title;

// most-used
MATCH (n:Knowledge {org_uid:$org})
RETURN n.title, n.use_count ORDER BY n.use_count DESC LIMIT 20;

// memories with no embedding (would be invisible to vector search — a red flag)
MATCH (n:Knowledge {org_uid:$org}) WHERE n.embedding IS NULL AND n.type <> 'topic'
RETURN n.uid, n.title;

// orphans: memories under no topic
MATCH (n:Knowledge {org_uid:$org}) WHERE n.type <> 'topic'
  AND NOT (:Topic)-[:CONTAINS]->(n)
RETURN n.title, n.type;
```

### Topics & structure

```cypher
// topic tree with member counts
MATCH (t:Topic {org_uid:$org})
OPTIONAL MATCH (t)-[:CONTAINS]->(m:Knowledge)
RETURN t.title, count(m) AS members ORDER BY members DESC;

// a memory's parents and related nodes (no uids in the output)
MATCH (n:Knowledge {title:$title})
OPTIONAL MATCH (p:Topic)-[:CONTAINS]->(n)
OPTIONAL MATCH (n)-[:RELATES]-(r:Knowledge)
RETURN n.title, collect(DISTINCT p.title) AS topics, collect(DISTINCT r.title) AS related;
```

### Governance & provenance

```cypher
// Pollen pipeline
MATCH (c:Pollen {org_uid:$org}) RETURN c.status, count(*) ORDER BY count(*) DESC;

// provenance: who wrote what (model → account → person)
MATCH (n:Knowledge {org_uid:$org}) WHERE n.type <> 'topic'
OPTIONAL MATCH (a:Account {uid:n.created_by})
RETURN coalesce(n.created_by_model,'?') AS model, coalesce(a.name,'seed') AS account,
       coalesce(a.person,a.name,'—') AS person, count(*) AS c
ORDER BY c DESC;

// recent audit trail (titles, not uids)
MATCH (e:Audit {org_uid:$org})
OPTIONAL MATCH (a:Account)-[:DID]->(e)
OPTIONAL MATCH (k:Knowledge {uid:e.target})
RETURN e.at, e.action, a.name AS who, coalesce(k.title, e.target) AS subject
ORDER BY e.at DESC LIMIT 50;

// superseded (outdated) memories and what replaced them
MATCH (new:Knowledge)-[:SUPERSEDES]->(old:Knowledge {org_uid:$org})
RETURN old.title AS outdated, new.title AS current;
```

### Vector / full-text search by hand

```cypher
// nearest neighbours to a given memory (needs its embedding)
MATCH (src:Knowledge {title:$title})
CALL db.index.vector.queryNodes('knowledge_embedding', 10, src.embedding)
YIELD node, score
WHERE node.uid <> src.uid
RETURN node.title, round(score,3) AS score ORDER BY score DESC;

// BM25 keyword search
CALL db.index.fulltext.queryNodes('knowledge_fulltext', 'deploy AND caddy')
YIELD node, score RETURN node.title, score ORDER BY score DESC LIMIT 10;
```

### Careful writes (emergency only — prefer a migration)

```cypher
// mark a memory as deprecated (does NOT archive) — reversible
MATCH (n:Knowledge {uid:$uid}) SET n.lifecycle='deprecated';

// tenant-wide relabel example (the kind of thing db.py migrations do idempotently)
MATCH (c:Chore) REMOVE c:Chore SET c:Pollen;   // (already migrated; illustrative)
```

> If you find yourself wanting a bulk write, add it to the `MIGRATIONS` list in
> `components/db.py` instead — it runs idempotently inside the app on the next deploy, keeping the
> audit/embedding invariants intact. See **[OPERATIONS.md](OPERATIONS.md)**.
