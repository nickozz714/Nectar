# Troubleshooting & FAQ

## Connection & clients

**MCP tools show `FailedToOpenSocket` on macOS, but curl works.**
Known Claude Code CLI bug on macOS: the Bun binary lacks the Local Network entitlement, so macOS TCC
blocks connections to a **private IP** (192.168.x / 10.x / 172.16.x) — including over VPN
(10.x). Fix: run the MCP over a **localhost tunnel**. A launchd agent keeps
`ssh -N -L 8642:localhost:8642 user@host` up, and the MCP URL points at `http://localhost:8642/mcp`.
The recall hook can keep using the LAN IP (curl has network access). The install-zip sets this up
automatically on macOS.

**The bottom nav bar is hidden behind Safari's toolbar on iPhone.**
Fixed: the layout uses `100dvh` + `viewport-fit=cover` (with a `window.innerHeight` fallback for old
iOS). If you still see it, hard-refresh — Safari caches the page (pull to reload, or close and reopen
the tab).

**A generic MCP client can't connect over TLS.**
Use the HTTPS sidecar on `:8643` and point the client at `https://<host>:8643/mcp`. For a self-signed
cert, the client must trust it (or use the real cert you configured in Caddy).

## Data & recall

**Search returns nothing / a memory isn't found.**
- Check scope: you only see `org`, your `team`, or your own `account` memories.
- Check it has an embedding (direct writes to Neo4j skip embedding — see NEO4J.md). Run
  **Beheer → Onderhoud → Her-embedden** if you changed the embedding model.
- Repeated empty recalls are recorded as knowledge **gaps** (Inzicht) — that's the signal to add the
  missing knowledge.

**Recall feels noisy / too much irrelevant context.**
Lower `RECALL_MAX_MEMORIES` or raise `RECALL_REL_FLOOR`. Give the recall an **anchor** (project
topic) so project knowledge is preferred.

**A duplicate got rejected / two similar memories both got stored.**
The write-gate rejects ≥ `DEDUP_SIMILARITY_THRESHOLD` (0.92) and files a think-Pollen for the grey
band (0.85–0.92). Tune those thresholds if your corpus is dense; use `force=true` only deliberately.

## Governance

**Pollen never becomes actionable ("ready").**
It needs `CONSENSUS_THRESHOLD` independent votes (distinct accounts). For a solo/small setup set it
to **1** (Beheer → Instellingen). An `org_admin` can also "direct apply" an open Pollen.

**I can't resolve a near-duplicate merge.**
Producer ≠ reviewer: you can't UPDATE/DELETE a near-duplicate you wrote yourself — a different Swarm
member must judge it (you may still ADD/NOOP).

**Contradiction scan surfaces unrelated pairs.**
That's the deterministic candidate step; the Swarm judges them "compatible" and closes them. If it's
too noisy, raise `CONTRA_MIN_SIM` (Neo4j-score units; it was tuned to 0.82 for this reason).

## Deployment

**Data disappears on restart (cloud).**
The container filesystem is ephemeral. Mount a persistent volume at Neo4j's `/data` (Azure Files on
ACA, a PVC on K8s). See DEPLOYMENT.md.

**A restored instance can't read the vault.**
`SECRET_MASTER_KEY` didn't survive. Set it explicitly (don't rely on auto-gen) and back it up
off-box; a replacement instance needs the same key to decrypt existing secrets.

**Neo4j won't start / permission errors on OpenShift.**
The `restricted` SCC runs a random UID. Set `securityContext.fsGroup` so `/data` is group-writable,
or grant `anyuid` if the base image needs a fixed UID. Use `Recreate`/StatefulSet — never two pods on
the same PVC.

**Neo4j refuses to boot with a `No declared setting with name` error.**
The Neo4j docker entrypoint turns every `NEO4J_*` env var into a config setting. Client-style vars
(`NEO4J_URI/USER/PASSWORD`) must be stripped before the entrypoint (the image's `start.sh` handles
this with `env -u`).

## Where to look

- Health: `GET /health`. App logs: container stdout. Audit: `GET /graph/audit`.
- Everything the swarm is doing: the **Pollen** tab. Everything about the corpus: **Governance** +
  **Inzicht**.
