from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "change-me-neo4j"

    ADMIN_TOKEN: str = "change-me-admin-token"
    SECRET_MASTER_KEY: str = ""  # Fernet key; vault is disabled when empty

    # Embeddings: local in-process by default (fastembed) — the stack runs autonomously,
    # no cloud. An OpenAI-compatible EMBEDDINGS_BASE_URL overrides local mode.
    EMBEDDINGS_LOCAL: bool = True
    EMBEDDINGS_BASE_URL: str = ""
    EMBEDDINGS_API_KEY: str = ""
    EMBEDDINGS_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDINGS_DIM: int = 384

    # Freshness / decay
    FRESHNESS_HALF_LIFE_DAYS: float = 30.0
    STABLE_HALF_LIFE_DAYS: float = 365.0  # Convention/Decision decay much slower
    SEMANTIC_WEIGHT: float = 0.7
    FRESHNESS_WEIGHT: float = 0.3
    # Anchors are a preference, not a filter: nodes inside the project's anchored topic
    # subtree get a ranking bonus, everything else stays findable.
    ANCHOR_BOOST: float = 0.15
    DEDUP_SIMILARITY_THRESHOLD: float = 0.92
    # Grey zone: similar-but-not-identical writes are created AND flagged as a dedup
    # chore so the swarm reviews them.
    DEDUP_REVIEW_THRESHOLD: float = 0.80
    # New parent topics are matched semantically against existing topics first, to
    # prevent near-duplicate topic sprawl ("Fabric" vs "Fabric werkwijzen").
    TOPIC_SIMILARITY_THRESHOLD: float = 0.85
    MIN_TITLE_LENGTH: int = 8
    MIN_CONTENT_LENGTH: int = 40

    # Governance: distinct votes (account+model) before a mutation chore is actionable
    CONSENSUS_THRESHOLD: int = 2

    @property
    def embeddings_enabled(self) -> bool:
        return bool(self.EMBEDDINGS_MODEL) and (bool(self.EMBEDDINGS_BASE_URL) or self.EMBEDDINGS_LOCAL)


@lru_cache
def get_settings() -> Settings:
    return Settings()
