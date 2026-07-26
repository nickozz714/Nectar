"""Ranking (anchor + decision boost, touch-on-read) and the secrets vault."""
from __future__ import annotations

from src.services import memory_service, search_service, vault_service


def _mem(graph, acc, title, content, topics, type_="memory"):
    return memory_service.remember(graph, acc, type_, title, content, topics, scope="org")


def test_anchor_is_preference_not_filter(graph, account):
    acc = account()
    _mem(graph, acc, "Swinkels release werkwijze detail",
         "alpha beta gamma release werkwijze swinkels specifiek een twee", ["Swinkels"])
    _mem(graph, acc, "Krimpenerwaard release werkwijze detail",
         "alpha beta gamma release werkwijze krimpenerwaard specifiek drie vier", ["Krimpenerwaard"])

    res = search_service.search(graph, acc, "alpha beta gamma release werkwijze",
                                anchors=["Swinkels"], limit=10, touch=False)
    titles = [n["title"] for n in res if n["type"] == "memory"]
    # both findable, Swinkels ranked above Krimpenerwaard
    assert any("Swinkels" in t for t in titles)
    assert any("Krimpenerwaard" in t for t in titles)
    assert titles.index(next(t for t in titles if "Swinkels" in t)) < \
           titles.index(next(t for t in titles if "Krimpenerwaard" in t))


def test_decision_boost(graph, account):
    acc = account()
    _mem(graph, acc, "Memory met dezelfde kernwoorden hier",
         "alpha beta gamma memory variant een twee drie", ["T"], type_="memory")
    _mem(graph, acc, "Besluit met dezelfde kernwoorden hier",
         "alpha beta gamma besluit variant vier vijf zes", ["T"], type_="decision")
    res = search_service.search(graph, acc, "alpha beta gamma", limit=10, touch=False)
    ranked = [n for n in res if n["type"] in ("memory", "decision")]
    assert ranked[0]["type"] == "decision"


def test_touch_on_read_increments_use(graph, account):
    acc = account()
    node = _mem(graph, acc, "Memory die we gaan gebruiken vaak",
                "alpha beta gamma gebruik teller een twee drie", ["T"])
    from src.repository import graph_repo
    before = graph_repo.get_node(graph, acc, node["uid"])["use_count"]
    search_service.search(graph, acc, "alpha beta gamma gebruik", limit=5, touch=True)
    after = graph_repo.get_node(graph, acc, node["uid"])["use_count"]
    assert after > before


def test_vault_owner_grant_isolation(graph, account):
    owner = account("owner", role="member")
    other = account("other", role="member")
    vault_service.set_secret(graph, owner, "API_KEY", "s3cret")
    assert vault_service.get_secret(graph, owner, "API_KEY") == "s3cret"
    assert vault_service.get_secret(graph, other, "API_KEY") is None
    from src.repository import vault_repo
    vault_repo.grant_secret(graph, other.org_uid, "API_KEY", other.uid)
    assert vault_service.get_secret(graph, other, "API_KEY") == "s3cret"
