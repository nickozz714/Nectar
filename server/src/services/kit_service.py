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


# The helper scripts live GLOBALLY in ~/.hivemind/scripts/ (installed once per machine);
# projects only opt in. So the manifest targets that global location — shared by every
# hive-enabled project.
_SCRIPTS_DIR = "~/.hivemind/scripts"
_PURPOSE = {
    "hive_recall.sh": "Recall hook (UserPromptSubmit) — injects relevant hive memories every prompt.",
    "hive-skill-install.sh": "Load a shared skill from the hive into .claude/skills/ over HTTP.",
    "hive-update.sh": "Shell fallback for this same update (re-fetches the install package).",
    "hive-secret": "Fetch a vault secret into an env var (never prints values).",
    "hive-enable.sh": "Turn Nectar on for a project (wires .claude/settings.json + .mcp.json).",
    "hive-attach.sh": "Attach a local artifact to a node, or fetch one (add/list/get).",
}

_APPLY = (
    "Do NOT reproduce or write out any script bodies — the scripts are fetched to disk by a "
    "command; routing their contents through you is unnecessary and trips safety scanning.\n"
    "1) FILES — just run `command` (a single line: it runs the trusted updater, which curls "
    "the latest scripts to ~/.hivemind/scripts/). If that fails because the updater is not "
    "installed yet, run `bootstrap` once (it fetches only that one updater script), then run "
    "`command`. Bytes flow curl→disk, never through you. Each `files` entry carries a `sha256` "
    "and a `fetch` URL path ($HIVE_URL + fetch) if you want to verify.\n"
    "2) CONFIG — reconcile `config` (the Claude-side wiring) WITHOUT touching secrets. For "
    "each target file, read it, apply every `requirements` item, and write back only if "
    "something was missing or wrong. NEVER overwrite, print, or invent HIVE_TOKEN / HIVE_URL "
    "/ Authorization / the MCP url — preserve whatever is already there (on macOS the MCP url "
    "is a localhost tunnel; keep it). Merge into existing JSON; do not drop unrelated keys.\n"
    "Finally report a short summary: what you added, updated, or left unchanged (files AND "
    "config), and never reveal token values."
)

# The single command that refreshes everything: run the trusted local updater.
_COMMAND = "bash ~/.hivemind/scripts/hive-update.sh"

# One-time bootstrap when the updater itself is missing: fetch ONLY hive-update.sh (one file)
# from the server using the stored connection, then `command` runs it. No secrets in the text.
_BOOTSTRAP = (
    "python3 - <<'PY'\n"
    "import json, os, urllib.request\n"
    "c = json.load(open(os.path.expanduser('~/.hivemind/config.json')))\n"
    "req = urllib.request.Request(c['hive_url'].rstrip('/') + '/kit/file/hive-update.sh',\n"
    "                             headers={'Authorization': 'Bearer ' + c['hive_token']})\n"
    "d = os.path.expanduser('~/.hivemind/scripts'); os.makedirs(d, exist_ok=True)\n"
    "p = os.path.join(d, 'hive-update.sh')\n"
    "open(p, 'wb').write(urllib.request.urlopen(req, timeout=30).read()); os.chmod(p, 0o755)\n"
    "print('installed', p)\n"
    "PY"
)

_HOW = (
    "Nectar installs GLOBALLY once (~/.hivemind/scripts/ + the macOS tunnel); each project "
    "just opts in. hive_update covers the client-side integration: the global helper scripts "
    "(`files`, under ~/.hivemind/scripts/ — shared by every hive-enabled project) AND this "
    "project's Claude wiring (`config`: the recall hook in .claude/settings.json and the MCP "
    "server in .mcp.json). It does NOT touch the SSH tunnel (global, set up once) and does "
    "NOT manage CLAUDE.md — the operating instructions arrive as a system memory injected by "
    "the recall hook every prompt. Server tools/endpoints update on redeploy."
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
            "env.HIVE_PROJECT must be a project slug (scopes the active focus). If missing, "
            "set it to the lowercased, dash-sanitized basename of the project directory.",
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
            "mcpServers.hivemind.headers.\"X-Hive-Project\" must equal env.HIVE_PROJECT from "
            ".claude/settings.json (binds the active focus to this project). Add/fix it to "
            "match; do not touch the Authorization header.",
        ],
    },
}


def _scripts_from_zip() -> dict[str, bytes]:
    """{basename: raw bytes} for every file in the zip's scripts/ folder."""
    zpath = _zip_path()
    if zpath is None:
        return {}
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            if info.is_dir() or "/scripts/" not in info.filename:
                continue
            out[info.filename.rsplit("/", 1)[-1]] = zf.read(info.filename)
    return out


def read_kit_file(name: str) -> bytes | None:
    """Raw bytes of a single kit script, for the /kit/file/{name} download endpoint.
    Only names that actually exist in the package are served (no path traversal)."""
    return _scripts_from_zip().get(name)


def build_manifest() -> dict:
    """Self-describing update manifest. Scripts are FETCHED (sha256 + a download path), not
    inlined — so applying an update never routes script bodies through the model (faster,
    and byte-exact rather than re-transcribed)."""
    zpath = _zip_path()
    if zpath is None:
        return {"error": "install package not found on the server", "files": []}

    kit_version = hashlib.sha256(zpath.read_bytes()).hexdigest()[:12]
    files = [
        {
            "path": f"{_SCRIPTS_DIR}/{name}",
            "name": name,
            "purpose": _PURPOSE.get(name, "Nectar helper script."),
            "mode": "0755",
            "sha256": hashlib.sha256(body).hexdigest(),
            "fetch": f"/kit/file/{name}",
        }
        for name, body in sorted(_scripts_from_zip().items())
    ]
    return {
        "kit_version": kit_version,
        "how_it_works": _HOW,
        "apply_instructions": _APPLY,
        "command": _COMMAND,
        "bootstrap": _BOOTSTRAP,
        "files": files,
        "config": _CONFIG,
    }
