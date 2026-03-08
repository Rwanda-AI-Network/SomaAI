"""Cache configuration and initialization."""

import os
from dataclasses import dataclass, field


@dataclass
class CacheConfig:
    """Configuration for caching backends."""

    # Redis configuration
    redis_url: str = field(
        default_factory=lambda: os.getenv(
            "SOMAAI_REDIS__URL", "redis://localhost:6379/0"
        )
    )
    redis_password: str | None = field(
        default_factory=lambda: os.getenv("SOMAAI_REDIS__PASSWORD")
    )

    # TTL defaults (in seconds)
    query_ttl: int = 86400  # 24 hours
    embedding_ttl: int = 3600  # 1 hour (matches settings.py)
    retrieval_ttl: int = 3600  # 1 hour
    session_ttl: int = 3600  # 1 hour

    # Semantic cache settings
    semantic_enabled: bool = True
    similarity_threshold: float = 0.92
    embedding_dimension: int = 768

    # Cache namespace
    namespace: str = "somaai"

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Load configuration from environment variables."""
        # Use main settings if available
        try:
            from somaai.settings import settings as main_settings

            return cls(
                redis_url=main_settings.redis.cache_url,
                redis_password=(
                    main_settings.redis.password.get_secret_value()
                    if main_settings.redis.password
                    else None
                ),
                query_ttl=main_settings.cache.query_ttl,
                embedding_ttl=main_settings.cache.embedding_ttl,
                retrieval_ttl=main_settings.cache.retrieval_ttl,
                session_ttl=main_settings.cache.session_ttl,
                semantic_enabled=main_settings.cache.semantic_enabled,
                similarity_threshold=main_settings.cache.similarity_threshold,
                embedding_dimension=main_settings.cache.embedding_dimension,
                namespace=main_settings.cache.namespace,
            )
        except (ImportError, AttributeError):
            # Fallback to environment variables
            return cls(
                redis_url=os.getenv(
                    "SOMAAI_REDIS__CACHE_URL", "redis://localhost:6379/2"
                ),
                redis_password=os.getenv("SOMAAI_REDIS__PASSWORD"),
                query_ttl=int(os.getenv("SOMAAI_CACHE__QUERY_TTL", "86400")),
                embedding_ttl=int(os.getenv("SOMAAI_CACHE__EMBEDDING_TTL", "3600")),
                retrieval_ttl=int(os.getenv("SOMAAI_CACHE__RETRIEVAL_TTL", "3600")),
                session_ttl=int(os.getenv("SOMAAI_CACHE__SESSION_TTL", "3600")),
                semantic_enabled=(
                    os.getenv("SOMAAI_CACHE__SEMANTIC_ENABLED", "true").lower()
                    == "true"
                ),
                similarity_threshold=float(
                    os.getenv("SOMAAI_CACHE__SIMILARITY_THRESHOLD", "0.92")
                ),
                embedding_dimension=int(
                    os.getenv("SOMAAI_CACHE__EMBEDDING_DIM", "768")
                ),
                namespace=os.getenv("SOMAAI_CACHE__NAMESPACE", "somaai"),
            )


# Global config instance
_config: CacheConfig | None = None


def get_cache_config() -> CacheConfig:
    """Get or create the global cache configuration."""
    global _config
    if _config is None:
        _config = CacheConfig.from_env()
    return _config


def set_cache_config(config: CacheConfig) -> None:
    """Set the global cache configuration."""
    global _config
    _config = config
