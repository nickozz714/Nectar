"""The deterministic write-gate: quality, PII, dedup bands, sensitivity, topic reuse."""
from __future__ import annotations

import pytest

from src.services import memory_service


def _remember(graph, acc, title, content, topics, **kw):
    return memory_service.remember(graph, acc, kw.pop("type_", "memory"),
                                   title, content, topics, **kw)


def test_creates_node_and_topic(graph, account):
    acc = account()
    res = _remember(graph, acc, "Fabric deploy werkwijze acceptatie",
                    "Releases gaan via de acceptatie-workspace en dan promotie naar productie.",
                    ["Swinkels"])
    assert res["created"] is True
    assert res["topics"] == ["Swinkels"]


def test_pii_rejected(graph, account):
    acc = account()
    with pytest.raises(ValueError, match="PII"):
        _remember(graph, acc, "Contactpersoon voor toegang",
                  "Mail piet@example.com voor de toegang tot de omgeving.", ["Swinkels"])


def test_quality_gate_rejects_short(graph, account):
    acc = account()
    with pytest.raises(ValueError, match="[Tt]itle too short"):
        _remember(graph, acc, "kort", "een voldoende lange inhoud voor de contentcheck erbij", ["T"])
    with pytest.raises(ValueError, match="[Cc]ontent too short"):
        _remember(graph, acc, "voldoende lange titel hier", "te kort", ["T"])


def test_exact_duplicate_is_deduped(graph, account):
    acc = account()
    title = "Unieke kennis over ingestie pipelines"
    content = "De bronze laag wordt via de orchestrator pipelines geladen niet de directe ingest."
    first = _remember(graph, acc, title, content, ["Swinkels"])
    again = _remember(graph, acc, title, content, ["Swinkels"])
    assert first["created"] is True
    assert again["created"] is False
    assert again["existing_uid"] == first["uid"]


def test_grey_zone_creates_and_files_chore(graph, account):
    from src.repository import governance_repo

    acc = account()
    # Neo4j's vector index returns a cosine score normalized to (1+cos)/2, so the
    # thresholds live in that space. These two entries share 6 of 8 words -> raw cos
    # 0.75 -> index score 0.875, i.e. in [DEDUP_REVIEW 0.85, DEDUP_SIMILARITY 0.92).
    title = "titelwoorddeel"
    _remember(graph, acc, title,
              "woordaaa woordbbb woordccc woordddd woordeee woordfff woordggg", ["Onderwerp"])
    res = _remember(graph, acc, title,
                    "woordaaa woordbbb woordccc woordddd woordeee woordhhh wooooiii", ["Onderwerp"])
    assert res["created"] is True
    assert any("dedup" in n for n in res["notes"])
    chores = governance_repo.open_chores(graph, acc, limit=10)
    assert any(c["type"] == "dedup_merge" for c in chores)


def test_sensitivity_classification(graph, account):
    acc = account()
    plain = _remember(graph, acc, "Gewone werkwijze zonder geheimen",
                      "Dit is een normale notitie over onze manier van werken hier.", ["T"])
    secret = _remember(graph, acc, "Toegang tot de omgeving instellen",
                       "Zet het api-key token in de omgeving voordat je de tool draait.", ["T"])
    from src.repository import graph_repo
    assert graph_repo.get_node(graph, acc, plain["uid"])["sensitivity"] == "intern"
    assert graph_repo.get_node(graph, acc, secret["uid"])["sensitivity"] == "gevoelig"


def test_topic_reuse_prevents_sprawl(graph, account):
    acc = account()
    _remember(graph, acc, "Eerste fabric werkwijze memory",
              "Inhoud over fabric werkwijzen die lang genoeg is voor de gate.", ["Fabric werkwijzen"])
    res = _remember(graph, acc, "Tweede fabric werkwijze memory",
                    "Andere inhoud over fabric werkwijzen die ook lang genoeg is.", ["Fabric werkwijzen"])
    # exact same topic title -> merged, no near-duplicate topic created
    assert res["topics"] == ["Fabric werkwijzen"]
    topics = graph_repo_list_titles(graph, acc)
    assert topics.count("Fabric werkwijzen") == 1


def graph_repo_list_titles(graph, acc):
    from src.repository import graph_repo
    return [t["title"] for t in graph_repo.list_topics(graph, acc)]
