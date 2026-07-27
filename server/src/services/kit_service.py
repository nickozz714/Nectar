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
    "For each entry in `files`: ensure the parent directory of `path` exists, then compare "
    "the local file at `path` (relative to the project root) against `sha256`. "
    "If the file is missing → CREATE it with `content`. If it exists but the sha differs → "
    "OVERWRITE it with `content`. If the sha matches → leave it (report as unchanged). "
    "When `mode` is \"0755\", make the file executable. Never touch the token or other keys "
    "in .claude/settings.json / .mcp.json. Finally, report a short summary: what you added, "
    "what you updated, what was already current."
)

_HOW = (
    "This is the LOCAL-FILES layer of HiveMind updates. Two other layers update on their own: "
    "the operating instructions reach you via the recall hook (a system memory injected every "
    "prompt), and server tools/endpoints go live on redeploy (new MCP tools on reconnect). "
    "hive_update only refreshes the per-project scripts."
)


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
        "settings_check": (
            "Also verify (do not rewrite unless broken): .claude/settings.json has a "
            "UserPromptSubmit hook whose command ends in .hivemind/scripts/hive_recall.sh, "
            "and .mcp.json has an 'hivemind' server. Leave HIVE_TOKEN / Authorization as-is."
        ),
        "files": files,
    }
