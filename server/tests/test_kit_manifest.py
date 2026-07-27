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

    # the recall hook + helpers must be there, under the GLOBAL ~/.hivemind path
    for name in ("hive_recall.sh", "hive-skill-install.sh", "hive-update.sh", "hive-enable.sh"):
        path = f"~/.hivemind/scripts/{name}"
        assert path in files, f"{path} missing from manifest"
        entry = files[path]
        assert entry["mode"] == "0755"
        assert entry["content"], "content must be inlined so the LLM can write it"
        assert entry["purpose"]
        # the advertised sha256 must actually match the content the LLM will write
        assert entry["sha256"] == hashlib.sha256(entry["content"].encode()).hexdigest()
