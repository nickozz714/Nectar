"""hive_update's manifest: the self-describing client kit the LLM applies to refresh a
project (what/where/how). Reads the maintained install package baked next to the repo."""
from __future__ import annotations

import hashlib

import pytest


def test_manifest_lists_scripts_with_content_and_hashes():
    from src.services import kit_service

    if kit_service._zip_path() is None:
        pytest.skip("hivemind-install.zip not present (run installer/build.sh)")

    manifest = kit_service.build_manifest()
    assert manifest["kit_version"] and manifest["apply_instructions"]

    # config part: declarative wiring for settings.json + .mcp.json, WITHOUT secrets
    config = manifest["config"]
    assert config["settings_json"]["path"] == ".claude/settings.json"
    assert config["mcp_json"]["path"] == ".mcp.json"
    blob = str(config)
    assert "hive_recall.sh" in blob and "mcpServers" in str(config["mcp_json"])
    # the manifest advertises the token only as something to PRESERVE, via a placeholder
    assert "<token>" in blob

    files = {f["path"]: f for f in manifest["files"]}

    # scripts are FETCHED, not inlined — no bodies routed through the model
    assert manifest["bootstrap"] and "install.zip" in manifest["bootstrap"]
    for name in ("hive_recall.sh", "hive-skill-install.sh", "hive-update.sh", "hive-enable.sh"):
        path = f"~/.hivemind/scripts/{name}"
        assert path in files, f"{path} missing from manifest"
        entry = files[path]
        assert entry["mode"] == "0755" and entry["purpose"]
        assert "content" not in entry, "manifest must NOT inline script bodies"
        assert entry["fetch"] == f"/kit/file/{name}"
        # the advertised sha256 matches what the fetch endpoint serves
        served = kit_service.read_kit_file(name)
        assert served is not None and entry["sha256"] == hashlib.sha256(served).hexdigest()


def test_kit_file_endpoint(client):
    """The fetch endpoint serves a real script (account-gated) and 404s unknown names."""
    from src.services import kit_service
    if kit_service._zip_path() is None:
        import pytest
        pytest.skip("hivemind-install.zip not present")

    admin = client.post("/register", json={"name": "Alice"}).json()
    h = {"Authorization": f"Bearer {admin['token']}"}

    ok = client.get("/kit/file/hive_recall.sh", headers=h)
    assert ok.status_code == 200 and b"HIVE_URL" in ok.content
    assert client.get("/kit/file/nope.sh", headers=h).status_code == 404
    assert client.get("/kit/file/hive_recall.sh").status_code in (401, 403, 422)
