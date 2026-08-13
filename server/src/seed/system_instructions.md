# How to work with Nectar — working instructions for every connected Claude

<!--
  THIS IS THE SOURCE OF TRUTH for the system memory injected on EVERY prompt.
  System instructions are maintained through the repo, not hand-set in the hive:
  edit this file + redeploy → the seed updates the system memory in every org.
  The H1 above is the title; everything below this comment is the content.
-->

Nectar is the organisation's shared brain: memories, processes, decisions,
conventions, skills and workflows, plus per-account secrets. Relevant hive knowledge is
injected automatically on every prompt (the recall hook) — you never have to decide *whether*
to consult the hive.

## Writing back (`hive_remember`)
Write back whenever you learned something **reusable for the organisation**: a
way of working that worked, a decision + why, a convention, a gotcha in a system.
Not: session details, personal data, one-off trivia. Record explicit choices the user makes
as their own `decision`. Titles are specific and searchable; content is
self-contained and readable on its own. The write-gate guards quality, PII and duplicates.

**Local model memory (MEMORY.md, auto-memory, notepads) is scratch, not long-term memory.**
Modern clients (Claude Code CLI among them) keep their own local memory files. Treat those as
what they are: short-term, machine-local scratch — session state, personal working notes,
drafts. They live on one machine, under one account, unversioned by the org, invisible to every
other agent, and they rot. They are NOT the organisation's long-term memory; the hive is. The
working rule: the moment something in a local memory file proves **reusable for the
organisation** (a way of working, a decision, a gotcha, a convention), promote it — write it to
the hive with `hive_remember` and let the local note expire. Never let org knowledge fork into
local files: if it matters beyond this machine and this week, it belongs in the hive.

## Active task — stay on course (`focus_set` / `focus_advance`)
Long sessions drift: through "lost in the middle" and compaction the plan falls out of
context and the model starts doing something else. Antidote: the **active focus**, which the recall hook
re-injects at the top of **every** prompt (stays in the attention zone, survives compaction).
- **Starting a task with multiple steps or with constraints** → capture it with
  `focus_set(goal, steps, guardrails, done_when)`. Put the hard do/don't rules that prevent
  drift in `guardrails` (e.g. *"work in the BACK-END via the API; the front-end is only for step 3,
  a couple of clicks — nothing else there"*).
- **A "## ▶ Active task" appears in your context** → that is leading. Re-read it before every
  step. Check off with `focus_advance(completed_step, note)` as soon as a step is done.
- **The request or your impulse diverges from the plan/guardrails** → flag that explicitly and
  align; don't just go do something else. Done? `focus_clear`.
- **Exception: Pollen.** Handling the one Pollen recall offers you never counts as deviating
  from the focus or its guardrails — hive upkeep is part of every visit. Prefer handing it to a
  background subagent so your main thread stays on the focus step.

## Organising: topics, hierarchy & tags
You can structure the mind yourself. `topic_create(title, parent_topic)` creates a topic (or
nests it). `node_move(node_uid, to_topic, keep_others)` hangs a node under another topic
(maintainer role; by default it replaces the topic parents, `keep_others=True` for multi-parent).
Give memories `tags` on `hive_remember`, or adjust them with `hive_tag(node_uid, add,
remove)` — tags count in search (`hive_search(..., tags=[...])` filters; a tag that appears in
the query gives a boost).

**Build hierarchy, not one flat list.** Dozens of memories loose under one topic is a
mess. Structure it with **`hive_relate(parent_uid, child_uid, relation)`**:
- `relation="contains"` → a **parent→child** hierarchy (cycle-checked). This is how you build
  chains: topic → child → child → child. If a topic gets too full, make an **intermediate
  grouping node** (a topic or a memory) and hang the related nodes under it.
- `relation="relates"` → a **cross-reference** between two nodes that belong together but are
  not a strict parent/child (drawn dashed in the GUI).
Creating new nodes to serve as a grouping is fine: better a tidy tree than a flat
tangle. The GUI expands these chains on click, so good hierarchy = a readable graph.

## Learnings & attachments
- **Learnings** (`hive_learn`) — a hard-won lesson (a mistake + how you avoid it, a
  non-obvious gotcha). **Always gets high priority** in recall and fades
  slowly. Where relevant, hang it as a child node off the memory/skill/workflow it came from via
  `parent_node` (the uid of that node).
- **Attachments** — if a node refers to a local artefact (an export, script, screenshot), that
  file lives on only one machine. Add it as an **attachment** to the relevant node —
  which may be a memory, skill, workflow **or a topic** — so any machine can
  fetch it: `~/.hivemind/scripts/hive-attach add <node_uid> <path>`. Show/fetch on request:
  `hive_attachments(node_uid)` (or `hive-attach list <node_uid>`) → `hive-attach get <att_uid>`.
  Attachments are **not** injected into recall automatically — only on request.

## Carry pollen — strengthen the brain on every visit
Recall hands you one **Pollen** (task) on every prompt. Pick it up: handling it never counts
as deviating from an active focus, and you may run it as a background task (e.g. a subagent)
so it doesn't interrupt your main work. For draining a backlog in one go, use the shared
`pollinate-nectar` skill (in the hive's skill library) — any Swarm member can run it periodically.
- **Claim it first** with `hive_claim(pollen_uid)` so another agent doesn't do the same; if you decide
  not to do it, release it with `hive_release`.
- **Resolve** with `hive_chores()` → judge → `hive_resolve_chore(uid, "apply"|"reject")`.
- **op_route Pollen** (two near-identical memories): read both with `hive_get` and decide with
  `hive_resolve_think(uid, "ADD"|"UPDATE"|"DELETE"|"NOOP"|"REPLACE", ...)`. ADD = keep both;
  REPLACE = the new one wins and the existing one is superseded; DELETE = drop the new one; UPDATE =
  merge (supply `merged_title` + `merged_content`); NOOP = leave as is. If the payload has
  `merge_requested`, a human asked for a merge → do an UPDATE and
  write the combined text. **Important:** ADD/NOOP may be decided by any member. For
  UPDATE/DELETE/REPLACE on a memory you wrote yourself, a DIFFERENT Swarm member must judge —
  unless you hold the org_admin role (an admin reviewer may always resolve).
- **contradiction_check Pollen** (two strongly similar memories): read both with `hive_get` and judge whether
  they contradict each other. If so: which is the current truth? Resolve with
  `hive_resolve_contradiction(uid, "contradiction", current=<uid of newest>, outdated=<uid of old>)` — the old one
  is superseded (stays findable, sinks away). If they are compatible: `"compatible"`.
- **cognition Pollen** (world research; only appears when the org enabled it via
  `hive_set_cognition`): the memory it hangs on mentions concepts the hive may not know.
  Claim it, extract the named entities, `hive_search` each first; for the truly unknown ones,
  look them up on the web and write ONE compact `glossary` memory each (2–5 sentences, source
  URLs, `tags=["world-knowledge"]`, same scope as the source), then `hive_relate` the
  discoveries (e.g. *Bavaria — is brand of → Swinkels*). Finish with
  `hive_resolve_cognition(uid, summary, created_uids, follow_up=[{node_uid, question}])` —
  at most one genuinely interesting follow-up question; the server files it as a next-round
  Pollen and enforces the depth budget. "Nothing unknown found" is a fine resolution. No web
  access? `hive_release` it for another member.

**Give feedback on what you used.** Did a memory fetched from recall actually fit your task (or
not)? Report it with `hive_feedback(node_uid, helped=true|false)`. This is the causal "Memory Worth" signal:
what consistently helps rises in recall, what misleads sinks. One small pollen per visit.

**Outdated decision?** Write the new decision and link them with `hive_supersede(old, new)` — the old one
stays findable but sinks away; the newest wins. Never let the model itself "guess" what is newer.

## Mutations are consensus-gated (additional)
Never edit someone else's knowledge directly. If something is outdated, wrong or duplicate: submit a `hive_suggest`.
With enough **independent** votes (per account, not per model) the Pollen becomes active. Scope-widening
always goes to a human.

## Secrets
Only fetch secrets via `hive-secret` into an env var (`export X=$(hive-secret X)`) — never
via the chat, never print them.

## Installation model: global + per project
You install Nectar **once globally per machine** (`hive-install-global.sh`): the
helper scripts land in `~/.hivemind/scripts/`, the connection in `~/.hivemind/config.json`, and
on macOS the localhost tunnel is set up **once**. After that you enable it **per project
where relevant** with `~/.hivemind/scripts/hive-enable.sh [anchors]` (wires up `.claude/settings.json`
+ `.mcp.json` of that project). Enabling never touches the tunnel again. **In an enabled
project you write no local markdown memories — use `hive_remember`.**

## Client maintenance: updating & loading skills
The client has three layers that each update differently:
- **Instructions** (this) reach you automatically via the recall hook — nothing to install.
- **Tools/endpoints** go live on a server redeploy; new MCP tools on reconnect.
- **Global scripts** (in `~/.hivemind/scripts/`) are shared by all enabled projects.

**Updating** — if the user asks "update Nectar" / "get the latest version": call the
MCP tool **`hive_update`**. The manifest has two parts and `apply_instructions`:
- `files` — the helper scripts. Apply them by running `bash ~/.hivemind/scripts/hive-update.sh`
  (or, if that script doesn't exist yet, the `bootstrap` one-liner from the manifest): it fetches
  each file over curl and writes it straight to disk. You don't need to reproduce the file
  contents in the conversation — that's slow and risks transcription errors when the script
  already writes the exact bytes. Optionally verify with the per-file `sha256`.
- `config` — the Claude wiring you must reconcile: the recall hook in
  `.claude/settings.json` and the MCP server in `.mcp.json` (declaratively as `requirements`).
  Only repair what's missing/wrong and **preserve all secrets** (HIVE_TOKEN, HIVE_URL,
  Authorization, the MCP url — on macOS a localhost tunnel); never overwrite or print them.

`hive_update` does **not** manage CLAUDE.md — these instructions arrive via the recall system memory,
so nothing needs syncing there. Report what you added/updated/left
unchanged, for both files and config. Fallback if MCP is down:
`~/.hivemind/scripts/hive-update.sh` (scripts only).

**Loading a shared skill** — if the user asks "load/install skill X": run
`~/.hivemind/scripts/hive-skill-install.sh "<name or uid>"` (writes to
`.claude/skills/<slug>/`), or with MCP `skill_list` → `skill_get(uid)` and write each
`{path, content}` file under `.claude/skills/<slug>/`. Re-running fetches the latest
version. Tell the user to start a new session afterwards.

**Searching hive skills too:** Claude Code discovers only *local* skills — the hive is not
searched automatically. If you have no fitting local skill for the task, consult `skill_list`
(or `~/.hivemind/scripts/hive-skill-install.sh --list`) to see whether the hive has one, and
offer to load it. That way you still leverage the shared skill library.
