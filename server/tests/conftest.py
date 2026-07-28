"""Test harness for HiveMind.

Runs against a REAL Neo4j (a throwaway instance — every test wipes the database, so
never point NEO4J_URI at a populated hive). Embeddings are replaced by a deterministic
bag-of-words fake so semantic/dedup behaviour is reproducible and no model is downloaded.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import os

from cryptography.fernet import Fernet

# Configure the environment BEFORE any src import instantiates Settings().
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "testpassword")
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["SECRET_MASTER_KEY"] = Fernet.generate_key().decode()
os.environ["EMBEDDINGS_LOCAL"] = "true"
os.environ["EMBEDDINGS_MODEL"] = "test-fake"
os.environ["EMBEDDINGS_DIM"] = "64"
os.environ["CONSENSUS_THRESHOLD"] = "2"
os.environ["DEDUP_SIMILARITY_THRESHOLD"] = "0.92"
os.environ["DEDUP_REVIEW_THRESHOLD"] = "0.85"

import pytest  # noqa: E402

DIM = 64


def fake_embed(text: str) -> list[float]:
    """Normalized bag-of-words vector. Identical text -> cosine 1.0; k of n shared
    words -> cosine ~ k/n. Deterministic, no external model."""
    vec = [0.0] * DIM
    for word in text.lower().split():
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@pytest.fixture(autouse=True)
def _patch_embed(monkeypatch):
    from src.services import embeddings

    monkeypatch.setattr(embeddings, "embed", fake_embed)
    for name in ("memory_service", "search_service", "skill_service",
                 "reindex_service", "governance_service", "curation_service"):
        module = importlib.import_module(f"src.services.{name}")
        if hasattr(module, "embed"):
            monkeypatch.setattr(module, "embed", fake_embed, raising=False)


@pytest.fixture(autouse=True)
def _clean_db():
    from src.db.neo4j import graph_session, init_db

    init_db()  # constraints + vector index (idempotent)
    with graph_session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


@pytest.fixture
def graph():
    from src.db.neo4j import graph_session

    with graph_session() as session:
        yield session


@pytest.fixture
def org(graph):
    from src.repository import tenancy_repo

    o = tenancy_repo.create_org(graph, "TestOrg")
    t = tenancy_repo.create_team(graph, o["uid"], "Data")
    return {"org_uid": o["uid"], "team_uid": t["uid"]}


@pytest.fixture
def account(graph, org):
    from src.authentication.deps import AuthedAccount
    from src.repository import tenancy_repo

    def _make(name="nick", role="member", team=True):
        a = tenancy_repo.create_account(
            graph, org["org_uid"], name,
            org["team_uid"] if team else None, role, person=name.capitalize(),
        )
        return AuthedAccount(uid=a["uid"], org_uid=a["org_uid"],
                             team_uid=a["team_uid"], name=a["name"], role=a["role"])

    return _make


@pytest.fixture
def client():
    """Plain TestClient — NOT used as a context manager, so the app lifespan (which would
    load the real embedding model) does not run; init_db is handled by the fixture."""
    from fastapi.testclient import TestClient

    from src.main import app

    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer test-admin-token"}
