"""RAG retriever with hybrid search, metadata filtering, and fallback strategies.

Retrieves relevant curriculum documents based on query, grade, and subject.
Uses Decimal for precise score handling in critical comparisons.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)


class Retriever:
    """Document retriever with grade/subject filtering and fallback.

    Uses Qdrant vector store for semantic search with
    optional metadata filtering by grade level and subject.

    Implements fallback strategy when filters return insufficient results.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize retriever.

        Args:
            settings: Application settings (optional, uses global if None)
        """
        self._settings = settings
        self._store = None

    @property
    def settings(self):
        """Get settings."""
        if self._settings is None:
            from somaai.settings import settings
            self._settings = settings
        return self._settings

    @property
    def store(self):
        """Get or create Qdrant store."""
        if self._store is None:
            from somaai.modules.knowledge.stores.qdrant import QdrantStore
            self._store = QdrantStore(self.settings)
        return self._store

    async def retrieve(
        self,
        query: str,
        top_k: int = 15,
        grade: str | None = None,
        subject: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant documents.

        Args:
            query: User's question
            top_k: Number of documents to retrieve
            grade: Filter by grade level (e.g., "S1", "P6")
            subject: Filter by subject (e.g., "mathematics")

        Returns:
            List of documents with content, metadata, and scores
        """
        start_time = time.time()

        try:
            docs = await self.store.search(
                query=query,
                top_k=top_k,
                grade=grade,
                subject=subject,
            )

            # Log retrieval metrics
            latency_ms = (time.time() - start_time) * 1000
            top_score = docs[0].get("score", 0) if docs else 0

            logger.info(
                "retrieval",
                extra={
                    "query_length": len(query),
                    "docs_returned": len(docs),
                    "top_score": top_score,
                    "latency_ms": latency_ms,
                    "grade": grade,
                    "subject": subject,
                },
            )

            return docs

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    async def retrieve_with_fallback(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 15,
        min_score: Decimal = Decimal("0.3"),
        min_results: int = 3,
    ) -> list[dict]:
        """Retrieve with automatic fallback when filters return insufficient results.

        Fallback strategy:
        1. Try exact filters (grade + subject)
        2. If insufficient, try grade only
        3. If still insufficient, try no filters

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter
            top_k: Number of documents
            min_score: Minimum relevance score
            min_results: Minimum acceptable result count

        Returns:
            List of documents with fallback indicator in metadata
        """
        # Level 1: Try exact filters
        docs = await self.retrieve(query, top_k, grade, subject)
        docs = self._filter_by_score(docs, min_score)

        if len(docs) >= min_results:
            logger.debug(f"Exact filter returned {len(docs)} docs")
            return docs

        # Level 2: Try grade only (remove subject filter)
        if subject:
            logger.info(f"Fallback: removing subject filter for '{query[:50]}...'")
            docs = await self.retrieve(query, top_k, grade, None)
            # Relax score slightly for cross-subject search
            docs = self._filter_by_score(docs, min_score * Decimal("0.8"))

            if len(docs) >= min_results:
                for doc in docs:
                    doc.setdefault("metadata", {})["fallback_level"] = 1
                return docs

        # Level 3: No filters (last resort)
        if grade:
            logger.info(f"Fallback: removing all filters for '{query[:50]}...'")
            docs = await self.retrieve(query, top_k, None, None)
            # Lower threshold for fallback
            fallback_threshold = min_score * Decimal("0.5")
            docs = self._filter_by_score(docs, fallback_threshold)

            for doc in docs:
                doc.setdefault("metadata", {})["fallback_level"] = 2

        return docs

    def _filter_by_score(self, docs: list[dict], min_score: Decimal) -> list[dict]:
        """Filter documents by minimum score.

        Uses Decimal for precise score comparison.

        Args:
            docs: Documents with scores
            min_score: Minimum acceptable score (Decimal)

        Returns:
            Filtered documents
        """
        return [
            d for d in docs
            if Decimal(str(d.get("score", 0))) >= min_score
        ]

    async def retrieve_for_context(
        self,
        query: str,
        grade: str,
        subject: str,
        max_tokens: int = 4000,
        use_fallback: bool = True,
    ) -> tuple[list[dict], str]:
        """Retrieve and format documents for LLM context.

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter
            max_tokens: Maximum tokens for context
            use_fallback: Whether to use fallback strategy

        Returns:
            Tuple of (documents, formatted_context_string)
        """
        if use_fallback:
            docs = await self.retrieve_with_fallback(
                query=query,
                grade=grade,
                subject=subject,
            )
        else:
            docs = await self.retrieve(
                query=query,
                top_k=15,
                grade=grade,
                subject=subject,
            )

        # Format context with source references
        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough char-to-token ratio

        for doc in docs:
            title = doc['metadata'].get('title', 'Source')
            page = doc['metadata'].get('page_start', '?')
            source = f"[{title}, Page {page}]"
            chunk = f"{source}\n{doc['content']}\n"

            if total_chars + len(chunk) > char_limit:
                break

            context_parts.append(chunk)
            total_chars += len(chunk)

        return docs, "\n---\n".join(context_parts)

    async def health_check(self) -> dict:
        """Check retriever health.

        Returns:
            Health status dict
        """
        try:
            # Try a simple retrieval
            _ = await self.retrieve("test query", top_k=1)
            return {
                "status": "healthy",
                "vector_store": "connected",
                "test_retrieval": "success",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
