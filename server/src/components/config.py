from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime environment: "production" (default) or "development". Drives log format and
    # a couple of safety checks; keep prod defaults safe.
    ENV: str = "production"
    LOG_LEVEL: str = "INFO"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "change-me-neo4j"

    ADMIN_TOKEN: str = ""  # operator break-glass; when empty the /admin API is disabled
    SECRET_MASTER_KEY: str = ""  # Fernet key; auto-generated + persisted when empty
    HIVE_ORG_NAME: str = "Nectar"  # name of the org created by the first self-registration

    # Microsoft Entra (Azure AD) SSO — optional. Configure an app registration and set these.
    ENTRA_TENANT_ID: str = ""
    ENTRA_CLIENT_ID: str = ""
    ENTRA_CLIENT_SECRET: str = ""
    ENTRA_REDIRECT_URI: str = ""   # e.g. https://host/auth/entra/callback; else derived
    PUBLIC_BASE_URL: str = ""      # e.g. https://hive.example.com; for redirects
    # Any Microsoft user from the (single-tenant) app auto-gets a member account on first
    # login — the Entra tenant is the access boundary. Set false for invite-only-with-SSO.
    ENTRA_AUTO_PROVISION: bool = True

    @property
    def entra_enabled(self) -> bool:
        return bool(self.ENTRA_TENANT_ID and self.ENTRA_CLIENT_ID and self.ENTRA_CLIENT_SECRET)

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
    # Explicit decisions must surface faster than ordinary memories.
    DECISION_BOOST: float = 0.1
    # Learnings are always high priority — a hard-won lesson must surface above ordinary recall.
    LEARNING_BOOST: float = 0.3
    # A node whose tag appears in the search query gets a ranking nudge (tags count in search).
    TAG_BOOST: float = 0.12
    # Recall-hook injection budget (anti "context rot"): inject only a FEW, highly-relevant
    # memories. Hard cap on how many, plus a relative floor (drop anything scoring below this
    # fraction of the top hit) so weak near-misses never eat the context window.
    RECALL_MAX_MEMORIES: int = 6
    RECALL_REL_FLOOR: float = 0.45
    # A superseded memory (an older fact a newer one replaced) stays findable but is pushed
    # down hard in ranking, so the current truth wins deterministically — never by asking the
    # model to guess which is newest.
    SUPERSEDE_PENALTY: float = 0.6
    # Bloom lifecycle weighting in recall: mature knowledge (repeatedly used / swarm-validated)
    # surfaces above fresh, unconfirmed "captured" notes. Deprecated is pushed down hard.
    BLOOM_BOOST: dict = {"mature": 0.2, "validated": 0.1, "captured": -0.05, "deprecated": -0.6}
    # Importance pin (0..1, 0.5 = neutral). A maintainer can raise a critical memory or lower a
    # trivial one; it shifts recall ranking by IMPORTANCE_WEIGHT·(importance−0.5).
    IMPORTANCE_WEIGHT: float = 0.3
    # Outcome-based decay ("Memory Worth"): once a memory has ≥ OUTCOME_MIN_SAMPLES helped/
    # hurt votes, recall shifts by OUTCOME_WEIGHT·(worth−0.5), worth = pos/(pos+neg). Makes decay
    # causal (did it help) instead of mere popularity.
    OUTCOME_WEIGHT: float = 0.3
    OUTCOME_MIN_SAMPLES: int = 3
    # Max size of a single attachment (artifact) stored on a memory. Kept modest because the
    # bytes live in Neo4j (single store); link, don't attach, for anything larger.
    ATTACHMENT_MAX_MB: int = 15
    DEDUP_SIMILARITY_THRESHOLD: float = 0.92
    # Grey zone: similar-but-not-identical writes are created AND flagged as a dedup
    # chore so the swarm reviews them.
    DEDUP_REVIEW_THRESHOLD: float = 0.85
    # New parent topics are matched semantically against existing topics first, to
    # prevent near-duplicate topic sprawl ("Fabric" vs "Fabric werkwijzen").
    TOPIC_SIMILARITY_THRESHOLD: float = 0.85
    MIN_TITLE_LENGTH: int = 8
    MIN_CONTENT_LENGTH: int = 40

    # Governance: distinct votes (account+model) before a mutation chore is actionable.
    # Set to 1 for a small/solo org so a single suggestion becomes 'ready' immediately.
    # (An org_admin can also directly resolve an 'open' chore, bypassing this — audited.)
    CONSENSUS_THRESHOLD: int = 2

    @property
    def embeddings_enabled(self) -> bool:
        return bool(self.EMBEDDINGS_MODEL) and (bool(self.EMBEDDINGS_BASE_URL) or self.EMBEDDINGS_LOCAL)

    @property
    def is_dev(self) -> bool:
        return self.ENV.lower().startswith("dev")


@lru_cache
def get_settings() -> Settings:
    return Settings()
