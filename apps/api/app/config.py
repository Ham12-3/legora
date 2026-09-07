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

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "legora"
    s3_secret_access_key: str = "legora-secret"
    s3_bucket: str = "legora-documents"
    s3_region: str = "us-east-1"

    # Never read by the web app. Never prefixed NEXT_PUBLIC_.
    openai_api_key: str | None = None
    model_router: str = "gpt-5-nano"
    model_extract: str = "gpt-5-mini"
    model_synth: str = "gpt-5"

    embed_model: str = "text-embedding-3-large"
    embed_dim: int = 1536

    # Bumping this invalidates the cell cache.
    prompt_version: str = "v1"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
