# Data Safety & Security

Nectar is an organisational memory: it holds decisions, know-how, and — in the vault — actual
secrets. Security is therefore a first-class concern, along three axes: **who can see what**
(tenancy), **who can do what** (auth & roles), and **where the data goes** (locality & exposure).

## The headline guarantee: nothing leaves your network

The server runs **no cloud LLM**. Embeddings and reranking are small local ONNX models baked into
the image; any heavier reasoning is delegated to the connected Swarm (the agents), not to a
server-side model. No memory, prompt, or secret is transmitted off-box by Nectar itself. The only
outbound call the server can make is to an **embeddings endpoint** — and only if you explicitly set
`EMBEDDINGS_LOCAL=false` and point `EMBEDDINGS_BASE_URL` at one. Default: fully local.

---

## 1. Tenancy & scope — who can see what

```
Org ──< Team ──< Account
```

Every memory has a **scope**: `org` (whole org), `team` (one team), or `account` (personal to one
identity). Every read in the repository layer applies a `VISIBLE` predicate:

```
n.scope = 'org'
  OR (n.scope = 'team'    AND n.team_uid = <caller.team>)
  OR (n.scope = 'account' AND n.created_by = <caller.account>)
```

There is no "fetch by id" that bypasses this — `hive_get`/`GET /graph/node/{uid}` also enforce
`VISIBLE`, so you cannot read a memory you aren't scoped to even if you know its uid. **Widening a
memory's scope is the one mutation that always requires a human** (the `awaiting_human` review
queue) — the Swarm can never broaden visibility on its own.

Cross-org isolation is by `org_uid` on every node and query; one org can never see another's data.

---

## 2. Authentication

Three first-class methods, all on by default, plus an optional SSO:

| Method | How | Notes |
|---|---|---|
| **First-run wizard** | first sign-up on an empty hive | becomes `org_admin` |
| **Password** | username + password | hashed with **scrypt**; per-IP brute-force lockout in the auth gate |
| **Account token** | `Authorization: Bearer <token>` | machine/agent identity |
| **Entra SSO** (optional) | Microsoft OAuth | enabled only when `ENTRA_*` are set; off otherwise |

**Tokens** are stored **hashed (sha256), never in plaintext** — a token value is shown exactly once,
at creation/rotation. Tokens support **labels, expiry, per-token role binding, rotation, revocation,
and cleanup**. Revoking a token cuts off that client immediately.

**Operator break-glass:** the `/admin` router is gated by a separate `ADMIN_TOKEN` **header** (not an
account). If `ADMIN_TOKEN` is empty (default), the entire `/admin` API is **disabled**. Everything a
day-to-day org admin needs is available through their normal account token under `/manage` — no
break-glass required.

---

## 3. Roles & authorisation

Ascending: **`member` < `maintainer` < `org_admin`**.

| Role | Can |
|---|---|
| `member` | read, write, give feedback, resolve *ready* Pollen |
| `maintainer` | + run maintenance scans, importance/decay/lifecycle/supersede/relate |
| `org_admin` | + review scope-widening, manage accounts/tokens/invites, backup/restore, audit, delete |

Role is enforced server-side (`assert_role`) on every privileged action; the GUI merely hides what
you can't do. **Producer ≠ reviewer** is enforced for destructive merges (`op_route` UPDATE/DELETE):
you cannot resolve a near-duplicate you wrote yourself.

---

## 4. The secrets vault

Per-account secrets (API keys, tokens) live in a **Fernet-encrypted** vault:

- **Encrypted at rest** with `SECRET_MASTER_KEY` (a Fernet key; auto-generated and persisted to the
  volume if unset — **back this up**, or a restored instance can't decrypt).
- **REST-only, never MCP.** There is deliberately **no MCP tool** that returns a secret value — so a
  secret can never land in an agent's chat context by accident. Secrets are injected into a client's
  environment by a helper script, not read into the model.
- **Per-secret grants.** An account only reads a secret it has been `GRANTED`.
- **Every read is audited.** Reading a secret writes an `:Audit` event.

---

## 5. Write-gate & content safety

Every write passes a deterministic gate (`services/memory_service.py`):

- **PII filter** — a regex pass blocks emails and similar personal identifiers from being stored.
- **Quality** — minimum title/content length; near-duplicate rejection.
- **Sensitivity classification** — memories are auto-labelled `intern` / `gevoelig` on
  credential-like patterns; `gevoelig` items are surfaced in the Governance dashboard for review.
  (Classification is a flag, not a block — real PII is blocked outright.)

---

## 6. The audit trail

An **append-only** `:Audit` log records every write, mutation, and secret access, with the acting
account and a timestamp. It is visible to `org_admin` (GUI **Governance → Audit-trail**, or
`GET /graph/audit`) and renders human-readable (titles, not uids). Combined with **provenance**
(every memory records model → account → person), you can answer "who wrote this, via which token,
and what happened to it since" — the lineage view.

---

## 7. Network exposure — hardening checklist

The container exposes four ports; treat them very differently:

| Port | Expose to | Never |
|---|---|---|
| `8642` (API/MCP/GUI) | clients, behind TLS + auth | plain HTTP over the internet |
| `8643` (HTTPS) | clients that need TLS | — |
| `7474` (Neo4j Browser) | **localhost / trusted admin only** | the public internet |
| `7687` (Bolt) | **trusted tooling over a tunnel** | the public internet |

**Checklist**
- [ ] Terminate **TLS** (Caddy sidecar, reverse proxy, or platform ingress) — never expose plain HTTP publicly.
- [ ] Set a strong **`NEO4J_PASSWORD`**; set **`SECRET_MASTER_KEY`** explicitly in multi-instance/cloud so a fresh replica can decrypt the vault.
- [ ] Keep **`ADMIN_TOKEN` empty** unless you truly need operator break-glass; if set, store it as a platform secret and rotate it.
- [ ] Keep **7474/7687 off the public internet** — LAN, VPN, or an SSH tunnel only.
- [ ] For remote access prefer a **VPN** or an authenticated reverse proxy over exposing the app directly.
- [ ] Set **`CONSENSUS_THRESHOLD ≥ 2`** in real multi-agent orgs so no single agent can push a change through unilaterally.
- [ ] **Back up** the `/data` volume *and* the `SECRET_MASTER_KEY` off-box (encrypted). The volume holds the graph and — if auto-generated — the vault key.
- [ ] Use **per-token roles** and short expiries for machine clients; rotate/revoke on offboarding.
- [ ] Keep embeddings **local** (`EMBEDDINGS_LOCAL=true`) unless you have a reason and a trusted endpoint.

---

## 8. Threat model (brief)

| Threat | Mitigation |
|---|---|
| A compromised agent tries to read everything | scope enforcement (`VISIBLE`) on every read; no by-id bypass; secrets never via MCP |
| A rogue/buggy agent pushes bad edits | consensus (distinct-account votes); scope-widening → human; producer ≠ reviewer; nothing hard-deleted |
| Token leak | hashed at rest, per-token expiry/role, instant revoke, audit of last-used |
| Data exfiltration to a cloud LLM | server is LLM-free; embeddings local by default; only opt-in external embeddings endpoint |
| Secret disclosure in chat | vault is REST-only; no MCP tool returns a secret value; every read audited |
| Store tampering | audit trail append-only; direct Bolt writes discouraged (see NEO4J.md); prefer app-side migrations |
| Lost host | volume + master-key backup enables full restore |

**Residual, by design:** Neo4j Community is single-node (no built-in encryption-at-rest of the store
files, no clustering) — put the volume on encrypted storage (LUKS / cloud disk encryption / Azure
Files with encryption) if you need at-rest guarantees, and rely on host-level backups for DR.
