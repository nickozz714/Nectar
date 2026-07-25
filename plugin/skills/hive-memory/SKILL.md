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
  `convention` (agreed style), `glossary` (term), `skill` (packaged instructions).
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
`hive_resolve_chore(uid, "apply"|"reject", note)`. The hive has no central maintainer —
upkeep is everyone's, done in passing.

## Secrets

Fetch secrets only via the `hive-secret` script into env vars
(`export X=$(hive-secret X)`) — never through chat context, never print values.
