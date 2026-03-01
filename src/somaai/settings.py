"""Application settings.

Centralized configuration loaded from environment variables.
"""

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SOMAAI_",  # Prevent collisions
    )

    # Application
    app_name: str = "SomaAI"
    version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./somaai.db",
        validation_alias=AliasChoices("SOMAAI_DATABASE_URL", "DATABASE_URL"),
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # Redis / Cache
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("SOMAAI_REDIS_URL", "REDIS_URL"),
    )
    redis_jobs_url: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("SOMAAI_REDIS_JOBS_URL", "REDIS_JOBS_URL"),
    )
    redis_cache_url: str = Field(
        default="redis://localhost:6379/2",
        validation_alias=AliasChoices("SOMAAI_REDIS_CACHE_URL", "REDIS_CACHE_URL"),
    )
    redis_password: SecretStr | None = None

    # Vector Database (Qdrant)
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias=AliasChoices("SOMAAI_QDRANT_URL", "QDRANT_URL"),
    )
    qdrant_api_key: SecretStr | None = None
    qdrant_collection_name: str = "somaai_documents"

    # Storage
    storage_backend: str = "minio"  # minio | s3

    # Ingestion Limits
    max_ingest_file_size: int = 100 * 1024 * 1024  # 100MB
    ingest_validation_threshold: int = 10 * 1024 * 1024  # 10MB

    # MinIO (Development)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "somaai-documents"
    minio_secure: bool = False

    # S3 (Production)
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_endpoint_url: str | None = None

    # Background Jobs
    queue_backend: str = "redis"  # redis | sync

    # Cache TTLs (seconds)
    cache_query_ttl: int = 86400
    cache_embedding_ttl: int = 3600
    cache_retrieval_ttl: int = 3600
    cache_session_ttl: int = 3600

    # RAG Settings
    rag_enable_input_validation: bool = True

    # LLM Backend
    llm_backend: str = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama3.2"
    huggingface_api_key: SecretStr | None = None
    huggingface_model: str = ""
    openai_api_key: SecretStr | None = None
    openai_model: str = ""

    # Security
    require_api_key: bool = False  # Enable in production


settings = Settings()
