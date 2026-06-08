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
    version: str = "0.1.1"

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

    # Storage (S3 - for production)
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_endpoint_url: str | None = None

    # LLM
    llm_backend: str = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-1.5-flash"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"

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
    api_keys: list[str] = []
    rate_limit_ask: str = "20/hour"
    rate_limit_create_conversation: str = "50/hour"
    session_cookie_secure: bool = False
    session_ttl_days: int = 90
    rag_enable_input_validation: bool = True
    rag_enable_hybrid_search: bool = True
    cors_allowed_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True

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

    @model_validator(mode="before")
    @classmethod
    def _parse_list_fields(cls, data: dict) -> dict:
        """Robustly parse list fields from JSON array or comma-separated string."""
        for field in ["api_keys", "cors_allowed_origins"]:
            val = data.get(field)
            if isinstance(val, str):
                import json

                try:
                    data[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    data[field] = [
                        item.strip()
                        for item in val.split(",")
                        if item.strip()
                    ]
        return data

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.is_testing:
            # Force SQLite for tests regardless of .env or current environment
            if not self.is_sqlite:
                self.database_url = "sqlite+aiosqlite:///:memory:"
                logger.info("Forcing SQLite in-memory for testing")
            # Always disable API keys for developer unit tests
            self.require_api_key = False

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
            # Security Hardening: Never allow default MinIO credentials in production
            if self.storage_backend == "minio":
                if self.minio_access_key == "minioadmin":
                    raise ValueError(
                        "Insecure default MinIO credentials ('minioadmin') are "
                        "prohibited in production. Set MINIO_ROOT_USER and "
                        "MINIO_ROOT_PASSWORD for the minio service, and "
                        "SOMAAI_MINIO_ACCESS_KEY/SOMAAI_MINIO_SECRET_KEY for the app."
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
