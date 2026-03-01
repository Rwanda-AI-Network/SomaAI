"""Application settings.

Centralized configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "SomaAI"
    version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./somaai.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # Redis / Cache
    redis_url: str = "redis://localhost:6379/0"  # General
    redis_jobs_url: str = "redis://localhost:6379/1"  # Job queue
    redis_cache_url: str = "redis://localhost:6379/2"  # RAG cache
    redis_password: str | None = None

    # Vector Database (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "somaai_documents"

    # Storage
    storage_backend: str = "minio"  # minio | s3

    # Ingestion Limits
    max_ingest_file_size: int = 100 * 1024 * 1024  # 100MB
    ingest_validation_threshold: int = 10 * 1024 * 1024  # 10MB

    # MinIO (Development)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "somaai-documents"
    minio_secure: bool = False

    # S3 (Production)
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_endpoint_url: str | None = None  # Custom endpoint (e.g. MinIO in prod)

    # Background Jobs
    queue_backend: str = "redis"  # redis | sync

    # Cache TTLs (seconds)
    cache_query_ttl: int = 86400  # Response cache: 24 hours
    cache_embedding_ttl: int = 3600  # Embedding cache: 1 hour
    cache_retrieval_ttl: int = 3600
    cache_session_ttl: int = 3600

    # RAG Settings
    rag_enable_input_validation: bool = True

    # LLM Backend
    llm_backend: str = "groq"  # groq | openai | huggingface | mock (tests only)
    groq_api_key: str | None = None
    groq_model: str = "llama3.2"
    huggingface_api_key: str | None = None
    huggingface_model: str = ""
    openai_api_key: str | None = None
    openai_model: str = ""

    # Security
    require_api_key: bool = False  # Enable in production


settings = Settings()
