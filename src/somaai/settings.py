"""Application settings.

Centralized configuration loaded from environment variables.
Uses Decimal for high-precision numeric configuration.
"""

from decimal import Decimal

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
    storage_backend: str = "local"  # local | gdrive
    storage_local_path: str = "./uploads"
    gdrive_credentials_path: str | None = None
    gdrive_folder_id: str | None = None

    # Background Jobs
    queue_backend: str = "redis"  # redis | sync

    # Cache TTLs (seconds)
    cache_query_ttl: int = 86400  # Response cache: 24 hours
    cache_embedding_ttl: int = 3600  # Embedding cache: 1 hour
    cache_retrieval_ttl: int = 3600
    cache_session_ttl: int = 3600

    # Cache quality thresholds
    response_cache_min_confidence: Decimal = Decimal("0.7")

    # Semantic Cache
    # cache_semantic_enabled: bool = True
    # cache_similarity_threshold: float = 0.92
    # cache_embedding_dim: int = 768
    # cache_namespace: str = "somaai"

    # LLM Backend
    llm_backend: str = "mock"  # mock | groq | openai | huggingface
    groq_api_key: str | None = None
    groq_model: str = "llama3.2"
    huggingface_api_key: str | None = None
    huggingface_model: str = ""
    openai_api_key: str | None = None
    openai_model: str = ""

    # Security
    require_api_key: bool = False  # Enable in production


settings = Settings()
