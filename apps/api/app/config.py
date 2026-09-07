"""Application configuration.

Every tunable lives here and comes from the environment. In particular:

* Model ids are keyed by ROLE, never inlined at a call site, because the
  OpenAI lineup changes faster than this codebase does.
* ``embed_dim`` is baked into the ``chunks.embedding`` column type. Changing it
  means re-embedding every chunk. See CLAUDE.md.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env first, then a service-local override if one exists.
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # "model_" is a protected namespace in pydantic; we deliberately use it
        # for the model-role settings below.
        protected_namespaces=(),
    )

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://legora:legora@localhost:5432/legora"
    redis_url: str = "redis://localhost:6379/0"

    # Two endpoints: the API talks to S3 over the docker network, but the
    # browser uploads via presigned URLs it must be able to resolve. SigV4 signs
    # the host, so presigned URLs are generated against the public one.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "legora"
    s3_secret_access_key: str = "legora-secret"
    s3_bucket: str = "legora-documents"
    s3_region: str = "us-east-1"

    # Shared with the Next.js server (and only the server). Signs the internal
    # JWT that carries (user_id, workspace_id) into every API request, and
    # gates the /auth endpoints that run before a user has a session.
    internal_api_secret: str = "dev-internal-secret-change-me-at-least-32-bytes"
    internal_token_max_age_seconds: int = 300

    presign_expiry_seconds: int = 900
    # Whether an object store is actually reachable. Off in tests: no HEAD
    # before registering a row, no orphan clean-up after a lost race.
    storage_enabled: bool = True
    max_upload_bytes: int = 200 * 1024 * 1024

    # Never read by the web app. Never prefixed NEXT_PUBLIC_.
    openai_api_key: str | None = None
    model_router: str = "gpt-5-nano"
    model_extract: str = "gpt-5-mini"
    model_synth: str = "gpt-5"

    embed_model: str = "text-embedding-3-large"
    embed_dim: int = 1536
    embed_batch_size: int = 96
    # "auto": OpenAI when a key is present, otherwise skip embeddings (chunks
    # still land, documents still reach "ready"). "fake": deterministic
    # vectors for tests. "none": always skip. "openai": always call.
    embeddings_provider: str = "auto"

    # Ingestion
    queue_enabled: bool = True
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    # A page with fewer extractable characters than this is treated as scanned.
    ocr_min_chars_per_page: int = 100
    chunk_target_tokens: int = 800
    chunk_max_tokens: int = 1500

    # Bumping this invalidates the cell cache.
    prompt_version: str = "v1"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
