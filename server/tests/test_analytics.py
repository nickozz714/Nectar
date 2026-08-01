"""Gap detection, analytics, and deterministic topic summaries."""
from __future__ import annotations

from src.repository import graph_repo
from src.services import curation_service, memory_service


def test_gap_recording_and_top(graph, account):
    acc = account("nick", role="member")
    graph_repo.record_gap(graph, acc.org_uid, "hoe doe ik iets onbekends")
    graph_repo.record_gap(graph, acc.org_uid, "hoe doe ik iets onbekends")
    graph_repo.record_gap(graph, acc.org_uid, "iets anders")
    gaps = graph_repo.top_gaps(graph, acc.org_uid, 10)
    assert gaps[0]["query"] == "hoe doe ik iets onbekends" and gaps[0]["count"] == 2


def test_analytics_shape(graph, account):
    acc = account("nick", role="member")
    memory_service.remember(graph, acc, "memory", "Een memory voor de analytics-test hier",
                            "Inhoud die lang genoeg is voor de write-gate, echt waar wel.", ["T"], scope="org")
    a = graph_repo.analytics(graph, acc.org_uid)
    assert a["total"] >= 1 and "most_used" in a and "gaps" in a


def test_topic_summary_built(graph, account):
    acc = account("nick", role="maintainer")
    memory_service.remember(graph, acc, "memory", "Item een onder samenvatting-topic hier",
                            "Inhoud die lang genoeg is voor de write-gate, echt waar wel.", ["SumTopic"], scope="org")
    curation_service.build_topic_summaries(graph, acc)
    t = graph_repo.get_topic_by_title(graph, acc.org_uid, "SumTopic")
    node = graph_repo.get_node(graph, acc, t["uid"])
    assert "1 items" in node["summary"] and "SumTopic" in node["summary"]
