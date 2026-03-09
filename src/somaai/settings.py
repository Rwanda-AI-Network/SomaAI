"""Application settings.

Single source of truth for all configuration. Uses pydantic-settings
to load from environment variables with the ``SOMAAI_`` prefix.

Environment variable format::

    SOMAAI_{FIELD_NAME}

Examples::

    SOMAAI_ENV=dev
    SOMAAI_DATABASE_URL=postgresql+asyncpg://user:pass@host/db
    SOMAAI_GROQ_API_KEY=gsk_...
"""

import logging
from enum import Enum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class AppEnv(str, Enum):
    """Application environment."""

    DEVELOPMENT = "dev"
    TESTING = "test"
    PRODUCTION = "prod"


class Settings(BaseSettings):
    """Flat application settings.

    Every field maps directly to ``SOMAAI_{FIELD_NAME}``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SOMAAI_",
        case_sensitive=False,
    )

    # Core
    env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "SomaAI"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    version: str = "0.1.0"

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./somaai.db",
        description="PostgreSQL for prod, SQLite for dev",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo_sql: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_jobs_url: str = "redis://localhost:6379/1"
    redis_cache_url: str = "redis://localhost:6379/2"
    redis_password: SecretStr | None = None

    # Vector DB (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "somaai_documents"

    # Storage (MinIO)
    storage_backend: str = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "somaai-documents"
    minio_secure: bool = False

    # LLM
    llm_backend: str = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    # Ingestion
    max_file_size: int = 100 * 1024 * 1024  # 100 MB
    ingest_validation_threshold: int = 1 * 1024 * 1024  # 1 MB
    max_chunk_size: int = 1500

    # Cache
    cache_query_ttl: int = 86400  # 24 h
    cache_embedding_ttl: int = 3600  # 1 h
    cache_retrieval_ttl: int = 3600
    cache_session_ttl: int = 3600
    cache_semantic_enabled: bool = True
    cache_similarity_threshold: float = 0.92
    cache_embedding_dimension: int = 768
    cache_namespace: str = "somaai"

    # Security
    require_api_key: bool = False
    rate_limit_ask: str = "20/hour"
    rate_limit_create_conversation: str = "50/hour"
    session_cookie_secure: bool = False
    session_ttl_days: int = 90
    rag_enable_input_validation: bool = True

    # Monitoring
    enable_metrics: bool = True

    # Derived helpers (not env vars)
    @property
    def is_production(self) -> bool:
        return self.env == AppEnv.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.env == AppEnv.TESTING

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def queue_backend(self) -> str:
        """Tests always use sync; everything else uses redis."""
        return "sync" if self.is_testing else "redis"

    # Validation

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.is_production:
            if self.is_sqlite:
                raise ValueError(
                    "SQLite is not allowed in production. "
                    "Set SOMAAI_DATABASE_URL to a PostgreSQL URL."
                )
            if not self.require_api_key:
                logger.warning(
                    "⚠️  SOMAAI_REQUIRE_API_KEY is False in production — "
                    "this is a security risk."
                )
            if not self.session_cookie_secure:
                logger.warning(
                    "⚠️  SOMAAI_SESSION_COOKIE_SECURE is False in production — "
                    "cookies will be sent over HTTP."
                )

        if self.debug:
            db_host = (
                self.database_url.split("@")[-1]
                if "@" in self.database_url
                else "sqlite"
            )
            logger.info(
                "Config [%s] DB=%s Debug=%s LLM=%s Storage=%s",
                self.env.value,
                db_host,
                self.debug,
                self.llm_backend,
                self.storage_backend,
            )

        return self


settings = Settings()
