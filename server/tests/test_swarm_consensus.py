"""Configurable Swarm consensus threshold + members resolving ready Pollen."""
from __future__ import annotations

import pytest

from src.repository import governance_repo, tenancy_repo
from src.services import governance_service, org_service


def _node(graph, acc):
    from src.services import memory_service
    return memory_service.remember(graph, acc, "memory", "Node voor een Pollen-test hier",
                                   "Inhoud die lang genoeg is voor de write-gate, echt waar wel.",
                                   ["T"], scope="org")


def test_threshold_one_makes_pollen_ready_on_single_vote(graph, account, org):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    node = _node(graph, admin)
    res = governance_service.suggest(graph, admin, "invalidate", node["uid"], {}, "weg ermee", "m")
    assert res["status"] == "ready"   # 1 vote is enough now


def test_default_threshold_needs_two_votes(graph, account):
    admin = account("nick", role="org_admin")     # org threshold unset → default (2)
    node = _node(graph, admin)
    res = governance_service.suggest(graph, admin, "invalidate", node["uid"], {}, "weg", "m")
    assert res["status"] == "open"    # a single vote is not enough at the default


def test_member_can_resolve_ready_pollen(graph, account, org):
    admin = account("nick", role="org_admin")
    org_service.set_consensus_threshold(graph, admin, 1)
    member = account("bee", role="member")
    node = _node(graph, member)
    pollen = governance_service.suggest(graph, member, "invalidate", node["uid"], {}, "archiveer", "m")
    assert pollen["status"] == "ready"
    out = governance_service.resolve(graph, member, pollen["uid"], "apply", "opgepakt")
    assert out["status"] == "resolved"   # member (not maintainer) resolved it


def test_set_consensus_requires_admin(graph, account):
    member = account("bee", role="member")
    with pytest.raises(ValueError, match="org_admin"):
        org_service.set_consensus_threshold(graph, member, 1)
