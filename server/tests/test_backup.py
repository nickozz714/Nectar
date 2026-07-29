"""Full-org export/import (backup & restore)."""
from __future__ import annotations

import pytest

from src.repository import backup_repo
from src.services import attachment_service, backup_service, memory_service


def _mem(graph, acc, title, content, topics, type_="memory", parent_node=""):
    return memory_service.remember(graph, acc, type_, title, content, topics, scope="org",
                                   parent_node=parent_node)


def _seed(graph, acc):
    base = _mem(graph, acc, "Werkwijze waar een backup-test op leunt",
                "Een proces dat we standaard volgen bij de implementaties hier.",
                ["Swinkels"], type_="process")
    child = _mem(graph, acc, "Les: maak altijd eerst een back-up",
                 "We verloren data door zonder back-up te draaien; maak er altijd eerst een.",
                 [], type_="learning", parent_node=base["uid"])
    attachment_service.save(graph, acc, base["uid"], "export.sql", "application/sql",
                            b"SELECT 1;\n")
    return base, child


def test_export_shape(graph, account):
    acc = account("nick", role="org_admin")
    _seed(graph, acc)
    dump = backup_service.export_org(graph, acc)
    assert dump["hivemind_export"] == backup_service.EXPORT_VERSION
    assert dump["counts"]["nodes"] >= 3          # topic + process + learning (+ seeded system)
    assert dump["counts"]["attachments"] == 1
    assert any(a["filename"] == "export.sql" for a in dump["attachments"])
    # relationships include the process->learning CONTAINS edge
    assert any(r["t"] == "CONTAINS" for r in dump["relationships"])


def test_export_requires_org_admin(graph, account):
    acc = account("bob", role="member")
    with pytest.raises(ValueError, match="org_admin"):
        backup_service.export_org(graph, acc)


def test_roundtrip_replace_restores(graph, account):
    acc = account("nick", role="org_admin")
    base, child = _seed(graph, acc)
    dump = backup_service.export_org(graph, acc)
    before = {n["uid"] for n in dump["nodes"]}

    # nuke it all, then restore
    backup_repo.wipe(graph, acc.org_uid)
    assert backup_service.export_org(graph, acc)["counts"]["nodes"] == 0

    result = backup_service.import_org(graph, acc, dump, replace=False)
    assert result["nodes"] == len(before)

    after = backup_service.export_org(graph, acc)
    assert {n["uid"] for n in after["nodes"]} == before
    assert after["counts"]["attachments"] == 1
    # attachment bytes survived
    data, name, _ = attachment_service.load(graph, acc, dump["attachments"][0]["uid"])
    assert data == b"SELECT 1;\n" and name == "export.sql"
    # the CONTAINS hierarchy survived
    assert any(r["t"] == "CONTAINS" and r["a"] == base["uid"] and r["b"] == child["uid"]
               for r in after["relationships"])


def test_import_idempotent(graph, account):
    acc = account("nick", role="org_admin")
    _seed(graph, acc)
    dump = backup_service.export_org(graph, acc)
    n1 = backup_service.import_org(graph, acc, dump, replace=False)["nodes"]
    n2 = backup_service.import_org(graph, acc, dump, replace=False)["nodes"]
    assert n1 == n2
    # no duplication after a second merge
    assert backup_service.export_org(graph, acc)["counts"]["nodes"] == len(dump["nodes"])


def test_import_rejects_bad_format(graph, account):
    acc = account("nick", role="org_admin")
    with pytest.raises(ValueError, match="format"):
        backup_service.import_org(graph, acc, {"nodes": []}, replace=False)
