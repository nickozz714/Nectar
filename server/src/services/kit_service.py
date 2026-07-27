from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

# The client "kit" (recall hook + helper scripts) that lives per project. Source of truth
# is the maintained install package baked into the image; hive_update reads it and returns
# a self-describing manifest so a connected LLM can materialize/refresh the files itself —
# no local update script required (that solves the bootstrap: the MCP connection is enough).


def _zip_path() -> Path | None:
    here = Path(__file__).resolve()
    # image: /app/hivemind-install.zip (parents[2]); repo: <root>/hivemind-install.zip (parents[3]).
    for cand in (here.parents[2] / "hivemind-install.zip",
                 here.parents[3] / "hivemind-install.zip"):
        if cand.exists():
            return cand
    return None


# Where each kit file belongs in the project, and what it is. Anything in the zip's
# scripts/ folder maps under .hivemind/scripts/ (the stable path the recall hook uses).
_PURPOSE = {
    "hive_recall.sh": "Recall hook (UserPromptSubmit) — injects relevant hive memories every prompt.",
    "hive-skill-install.sh": "Load a shared skill from the hive into .claude/skills/ over HTTP.",
    "hive-update.sh": "Shell fallback for this same update (re-fetches the install package).",
    "hive-secret": "Fetch a vault secret into an env var (never prints values).",
}

_APPLY = (
    "Apply in two parts.\n"
    "1) FILES — for each entry in `files`: ensure the parent dir of `path` exists, then "
    "compare the local file against `sha256`. Missing → CREATE with `content`; sha differs "
    "→ OVERWRITE with `content`; sha matches → leave it. Make `mode` \"0755\" files "
    "executable.\n"
    "2) CONFIG — reconcile `config` (the Claude-side wiring) WITHOUT touching secrets. For "
    "each target file, read it, apply every `requirements` item, and write back only if "
    "something was missing or wrong. NEVER overwrite, print, or invent HIVE_TOKEN / HIVE_URL "
    "/ Authorization / the MCP url — preserve whatever is already there (on macOS the MCP url "
    "is a localhost tunnel; keep it). Merge into existing JSON; do not drop unrelated keys.\n"
    "Finally report a short summary: what you added, updated, or left unchanged (files AND "
    "config), and never reveal token values."
)

_HOW = (
    "hive_update covers the CLIENT-SIDE integration of HiveMind in this project: the helper "
    "scripts (`files`) AND the Claude wiring (`config`: the recall hook in "
    ".claude/settings.json and the MCP server in .mcp.json). It does NOT manage CLAUDE.md — "
    "the operating instructions are delivered as a system memory injected by the recall hook "
    "every prompt, so there is nothing to sync into CLAUDE.md. Server tools/endpoints update "
    "on redeploy (new MCP tools on reconnect); those need no client action either."
)

# Declarative spec of the Claude-side wiring. Secrets (token/url) are intentionally NOT
# included — the LLM preserves whatever the install already put there.
_CONFIG = {
    "settings_json": {
        "path": ".claude/settings.json",
        "format": "json",
        "requirements": [
            "env.HIVE_ENABLED must equal \"1\".",
            "env.HIVE_URL and env.HIVE_TOKEN must be present — PRESERVE existing values, "
            "never overwrite or print them. env.HIVE_ANCHORS may exist; keep it.",
            "hooks.UserPromptSubmit must contain a command hook whose command ends with "
            "\".hivemind/scripts/hive_recall.sh\". Add it if missing; fix the path if it "
            "points at an old location; do not duplicate it.",
        ],
    },
    "mcp_json": {
        "path": ".mcp.json",
        "format": "json",
        "requirements": [
            "mcpServers.hivemind must exist with type \"http\" and a headers.Authorization "
            "of \"Bearer <token>\". PRESERVE the existing url and token exactly (the url may "
            "be a http://localhost:<port>/mcp tunnel on macOS); only add the entry if it is "
            "entirely missing.",
        ],
    },
}


def build_manifest() -> dict:
    """Return the current client kit as a self-describing manifest (what, where, how)."""
    zpath = _zip_path()
    if zpath is None:
        return {"error": "install package not found on the server", "files": []}

    raw = zpath.read_bytes()
    kit_version = hashlib.sha256(raw).hexdigest()[:12]

    files: list[dict] = []
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir() or "/scripts/" not in name:
                continue
            base = name.rsplit("/", 1)[-1]
            content = zf.read(name).decode("utf-8")
            files.append({
                "path": f".hivemind/scripts/{base}",
                "purpose": _PURPOSE.get(base, "HiveMind helper script."),
                "mode": "0755",
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content": content,
            })
    files.sort(key=lambda f: f["path"])

    return {
        "kit_version": kit_version,
        "how_it_works": _HOW,
        "apply_instructions": _APPLY,
        "files": files,
        "config": _CONFIG,
    }
