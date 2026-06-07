"""SomaAI caching module.

Uses:
- aiocache: General-purpose async caching with Redis backend
- gptcache: Semantic caching for LLM responses
"""

from somaai.cache.config import CacheConfig, get_cache_config
from somaai.cache.decorators import cached_embedding, cached_query, cached_retrieval

__all__ = [
    # Config
    "CacheConfig",
    "get_cache_config",
    # Decorators
    "cached_query",
    "cached_embedding",
    "cached_retrieval",
]
