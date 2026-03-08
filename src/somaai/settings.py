from enum import Enum
import logging
from typing import Annotated, Literal

from pydantic import (
    Field,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    """Application environment."""
    DEVELOPMENT = "dev"
    TESTING = "test"
    PRODUCTION = "prod"


class IngestSettings(BaseSettings):
    """Ingestion pipeline configurations."""
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    validation_threshold: int = 1 * 1024 * 1024  # 1MB
    max_chunk_size: int = 1500
    
    # Streaming optimization settings
    use_optimized_streaming: bool = True  # Feature flag
    use_pikepdf: bool = True  # Use fast C++ PDF parser
    
    # Temporary file management
    temp_dir: str | None = None  # Custom temp directory (None = system default)
    temp_prefix: str = "somaai_"  # Prefix for temp files
    temp_cleanup_on_error: bool = True  # Auto-cleanup on errors
    temp_max_age_hours: int = 24  # Max age before cleanup
    
    # Streaming buffer settings
    stream_buffer_small_threshold: int = 10 * 1024 * 1024  # 10MB
    stream_buffer_spool_threshold: int = 10 * 1024 * 1024  # 10MB RAM before spill
    stream_chunk_size: int = 64 * 1024  # 64KB chunks
    stream_force_disk_threshold: int = 100 * 1024 * 1024  # 100MB
    
    # Parallel processing
    max_parallel_pages: int = 4  # Max parallel page extraction
    enable_parallel_extraction: bool = True


class CacheSettings(BaseSettings):
    """RAG and Generic Cache configurations."""
    query_ttl: int = 86400  # 24 hours
    embedding_ttl: int = 3600  # 1 hour
    retrieval_ttl: int = 3600
    session_ttl: int = 3600
    semantic_enabled: bool = True
    similarity_threshold: float = 0.92
    embedding_dimension: int = 768
    namespace: str = "somaai"


class ServerSettings(BaseSettings):
    """Web server configurations."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    version: str = "0.1.0"
    queue_backend: str = "redis"  # "redis" or "sync" (sync for testing)


class DatabaseSettings(BaseSettings):
    """Database connection and pooling configurations."""
    url: str = Field(default="sqlite+aiosqlite:///./somaai.db")
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    echo_sql: bool = False


class RedisSettings(BaseSettings):
    """Redis connection configurations."""
    url: str = "redis://localhost:6379/0"
    jobs_url: str = "redis://localhost:6379/1"
    cache_url: str = "redis://localhost:6379/2"
    password: SecretStr | None = None


class QdrantSettings(BaseSettings):
    """Vector database (Qdrant) configurations."""
    url: str = "http://localhost:6333"
    api_key: SecretStr | None = None
    collection_name: str = "somaai_documents"
    rag_enable_hybrid_search: bool = False


class StorageSettings(BaseSettings):
    """Object storage configurations (MinIO/S3)."""
    backend: Literal["minio", "s3"] = "minio"
    
    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "somaai-documents"
    minio_secure: bool = False

    # S3
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_endpoint_url: str | None = None


class LLMSettings(BaseSettings):
    """LLM Backend configurations."""
    backend: str = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama3.2"
    huggingface_api_key: SecretStr | None = None
    huggingface_model: str = ""
    openai_api_key: SecretStr | None = None
    openai_model: str = ""


class SecuritySettings(BaseSettings):
    """Security and Session configurations."""
    require_api_key: bool = False
    rate_limit_ask: str = "20/hour"
    rate_limit_create_conversation: str = "10/hour"
    session_cookie_secure: bool = False
    session_ttl_days: int = 90
    rag_enable_input_validation: bool = True


class Settings(BaseSettings):
    """Main Application Settings."""
    
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SOMAAI_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "SomaAI"
    
    # Sub-models
    server: ServerSettings = ServerSettings()
    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    qdrant: QdrantSettings = QdrantSettings()
    storage: StorageSettings = StorageSettings()
    llm: LLMSettings = LLMSettings()
    ingest: IngestSettings = IngestSettings()
    cache: CacheSettings = CacheSettings()
    security: SecuritySettings = SecuritySettings()

    # Shared / Global context
    enable_metrics: bool = True

    @model_validator(mode="after")
    def validate_and_log(self) -> "Settings":
        # Global validation rules
        if self.env == AppEnv.PRODUCTION:
            if self.db.url.startswith("sqlite"):
                raise ValueError("SQLite is not allowed in production environment")
            if not self.security.session_cookie_secure:
                # We could warn or enforce here. Let's enforce for principal status.
                self.security.session_cookie_secure = True
                
        if self.server.debug:
            logger = logging.getLogger("somaai.settings")
            db_host = self.db.url.split("@")[-1] if "@" in self.db.url else "sqlite"
            logger.info(
                "Config Loaded [%s] - DB: %s, Debug: %s", 
                self.env.value, db_host, self.server.debug
            )
        return self


settings = Settings()
