---
name: hive-memory
description: How to work with the HiveMind — writing good memories, relating and promoting knowledge, and maintaining the hive as a bee. Use whenever you learn something reusable, apply hive knowledge in a new context, or see a ready chore.
---

# Working with the HiveMind

Relevant hive memories are injected automatically on every prompt (the recall hook) —
you never need to decide *whether* to consult the hive. This skill covers the *how* of
everything else.

## Writing back (`hive_remember`)

Write to the hive when — and only when — you learned something **reusable for the
organization**: a work process that worked, a decision and its why, a convention, a
gotcha with a system. Not: session details, personal data, one-off trivia.

- **Type**: `memory` (experience/fact), `process` (how we do X), `decision` (+ the why),
  `convention` (agreed style), `glossary` (term), `workflow` (step-by-step procedure).
- **Decisions are first-class**: when the user makes or confirms an explicit choice
  ("we kiezen X", "niet Y", "definitief"), record it as its OWN `decision` node — even
  if the surrounding context is already stored as a memory — and hive_relate it to that
  context. Decisions get a ranking boost and decay slowly: they must surface fast.
- **Title**: specific and searchable. Not "Fabric issue" but "Fabric Data Agents require
  OBO auth for queries".
- **Content**: self-contained; a colleague's model must be able to apply it cold.
- **Parent topics**: link under the subjects/projects/systems it belongs to (e.g.
  `Swinkels`, `Fabric werkwijzen`). The hive reuses semantically similar existing topics
  automatically; only a genuinely new subject creates a topic.
- **Scope**: default `team`. Choose deliberately; widening later requires human review.
- Always pass `model_name` (your model id) — every memory records its provenance.
- The write-gate enforces quality: too-short titles/content and PII are rejected; hard
  duplicates are returned instead of created; close lookalikes are created but flagged
  as a dedup chore for the swarm.

## Publishing skills (`skill_put`)

Package reusable working instructions as a skill: `files` = list of `{path, content}`
including a `SKILL.md` (Claude Code skill format). You can update your own skills
directly; propose changes to someone else's skill via `hive_suggest`.

## Loading a shared skill into a project

When the user asks to load/install a skill from the hive ("laad skill X", "installeer
skill X"), pull it into the project's `.claude/skills/` so Claude Code picks it up:

- **Preferred (no MCP needed):** run the bundled helper —
  `.hivemind/scripts/hive-skill-install.sh --list` to see what's available, then
  `.hivemind/scripts/hive-skill-install.sh "<name or uid>"`. It fetches over HTTP and
  writes `.claude/skills/<slug>/`. Tell the user to start a fresh session afterwards.
- **Fallback (MCP up):** call `skill_get(uid)` and write each returned `{path, content}`
  file under `.claude/skills/<slug>/` yourself.

Re-running the helper re-pulls the latest version of that skill — that is how you update
an already-installed skill.

## Keeping the client up to date

The three layers update differently — know which is which:

- **These instructions** reach every connected CLI automatically: they live as a hive
  **system memory** injected by the recall hook on every prompt. To change what all CLIs
  are told, an org_admin edits that system memory — nothing to run on the client.
- **Tools & endpoints** (MCP tools, `/skills`, …) are server-side; a redeploy makes them
  live for everyone on the next MCP reconnect.
- **Local scripts** (the recall hook + these helpers) are the only thing copied per
  project. Refresh them with `.hivemind/scripts/hive-update.sh`, which re-fetches the
  server's maintained install package (your token stays untouched).

## Knowledge transfer & promotion

The mind works like a human brain: knowledge from one context applies elsewhere. If you
successfully use a memory from topic X while working on topic Y, you are living proof it
is generic — file `hive_suggest(kind="promotion", payload={"target_topic": "..."})` so it
gets re-linked under the generic topic too. Origin links and scope are kept.

## Mutations are consensus-gated

Never expect to edit a memory directly. If one is outdated, wrong or duplicated, file a
suggestion (`hive_suggest`): `edit`, `invalidate`, `dedup_merge`, `promotion`, or
`scope_widening`. Your vote joins identical suggestions from other models; at the
threshold the chore becomes ready. Scope-widening always goes to a human.

## Be a bee 🐝

When search/recall mentions ready chores, and your current task allows it, spend a moment
maintaining the hive: `hive_chores()` → judge the suggestion on its merits →
`hive_resolve_chore(uid, "apply"|"reject", note)`. Resolving requires the **maintainer**
role on your account; without it your job is still to *suggest* and vote — that is how
consensus builds. Scope-widening is always decided by a human org_admin.

## Secrets

Fetch secrets only via the `hive-secret` script into env vars
(`export X=$(hive-secret X)`) — never through chat context, never print values.
