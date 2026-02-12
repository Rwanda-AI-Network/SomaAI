"""Cache configuration and initialization."""

import os
from dataclasses import dataclass, field


@dataclass
class CacheConfig:
    """Configuration for caching backends."""

    # Redis configuration
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    redis_password: str | None = field(
        default_factory=lambda: os.getenv("REDIS_PASSWORD")
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
                redis_url=main_settings.redis_cache_url,
                redis_password=main_settings.redis_password,
                query_ttl=main_settings.cache_query_ttl,
                embedding_ttl=main_settings.cache_embedding_ttl,
                retrieval_ttl=main_settings.cache_retrieval_ttl,
                session_ttl=main_settings.cache_session_ttl,
                semantic_enabled=(
                    os.getenv("CACHE_SEMANTIC_ENABLED", "true").lower() == "true"
                ),
                similarity_threshold=float(
                    os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92")
                ),
                embedding_dimension=int(os.getenv("CACHE_EMBEDDING_DIM", "768")),
                namespace=os.getenv("CACHE_NAMESPACE", "somaai"),
            )
        except ImportError:
            # Fallback to environment variables
            return cls(
                redis_url=os.getenv("REDIS_CACHE_URL", "redis://localhost:6379/2"),
                redis_password=os.getenv("REDIS_PASSWORD"),
                query_ttl=int(os.getenv("CACHE_QUERY_TTL", "86400")),
                embedding_ttl=int(os.getenv("CACHE_EMBEDDING_TTL", "3600")),
                retrieval_ttl=int(os.getenv("CACHE_RETRIEVAL_TTL", "3600")),
                session_ttl=int(os.getenv("CACHE_SESSION_TTL", "3600")),
                semantic_enabled=(
                    os.getenv("CACHE_SEMANTIC_ENABLED", "true").lower() == "true"
                ),
                similarity_threshold=float(
                    os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92")
                ),
                embedding_dimension=int(os.getenv("CACHE_EMBEDDING_DIM", "768")),
                namespace=os.getenv("CACHE_NAMESPACE", "somaai"),
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
