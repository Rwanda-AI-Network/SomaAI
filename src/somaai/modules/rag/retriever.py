"""RAG retriever with metadata filtering and fallback strategies.

Retrieves relevant curriculum documents based on query and grade level.
Uses Qdrant vector store with cosine similarity for semantic search.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)


class Retriever:
    """Document retriever with dense semantic search and metadata filtering.

    Uses Qdrant vector store with cosine similarity for semantic search.
    Supports metadata filtering by grade level.

    Fallback Strategy:
        Level 1: grade filter
        Level 2: no filters (if <3 results)
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
        top_k: int = 8,
        grade: str | None = None,
        subject: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant documents using dense semantic search.

        Args:
            query: User's question
            top_k: Number of documents to retrieve
            grade: Filter by grade level (e.g., "S1", "P6")
            subject: Subject filter (reserved for future use, not applied)

        Returns:
            List of documents with content, metadata, and scores
        """
        # Input validation
        if getattr(self.settings, "rag_enable_input_validation", True):
            if not query or not query.strip():
                logger.warning("Empty query provided to retriever")
                return []

            if top_k < 1:
                logger.warning("Invalid top_k=%d, using default 8", top_k)
                top_k = 8

            if top_k > 100:
                logger.warning("top_k=%d exceeds maximum, capping at 100", top_k)
                top_k = 100

            query = query.strip()

        # Normalize metadata filters to canonical casing.
        # Grade: UPPERCASE (matches GradeLevel enum: P6, S1, S6)
        # Subject: lowercase (matches Subject enum: computer_science)
        if grade:
            grade = grade.strip().upper()
        if subject:
            subject = subject.strip().lower()

        start_time = time.time()

        try:
            # Dense retrieval using Qdrant vector store
            # NOTE: subject filter disabled for now — only grade is applied.
            # Subject filtering will be re-enabled once ingestion metadata
            # is aligned with frontend selections.
            docs = await self.store.search(
                query=query,
                top_k=top_k,
                grade=grade,
                subject=None,  # Disabled: subject filter not yet supported
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
                },
            )

            return docs

        except ConnectionError as e:
            logger.error("Qdrant connection failed: %s", e)
            return []

        except TimeoutError as e:
            logger.error("Qdrant request timeout: %s", e)
            return []

        except ValueError as e:
            logger.error("Invalid parameters for retrieval: %s", e)
            return []

        except Exception as e:
            logger.error("Retrieval failed with unexpected error: %s", e, exc_info=True)
            return []

    async def retrieve_with_fallback(
        self,
        query: str,
        grade: str | None = None,
        subject: str | None = None,
        top_k: int = 8,
        min_score: float = 0.3,
        min_results: int = 3,
    ) -> list[dict]:
        """Retrieve with automatic fallback when filters return insufficient results.

        Fallback strategy:
        1. Try with grade filter
        2. If insufficient results, try with no filters

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter (reserved for future use)
            top_k: Number of documents
            min_score: Minimum relevance score
            min_results: Minimum acceptable result count

        Returns:
            List of documents with fallback indicator in metadata
        """
        # Input validation
        if not query or not query.strip():
            logger.warning("Empty query in retrieve_with_fallback")
            return []

        # Normalize metadata filters to canonical casing
        if grade:
            grade = grade.strip().upper()
        if subject:
            subject = subject.strip().lower()

        if min_results < 1:
            logger.warning("Invalid min_results=%d, using default 3", min_results)
            min_results = 3

        if min_score < 0.0 or min_score > 1.0:
            logger.warning("Invalid min_score=%.2f, using default 0.3", min_score)
            min_score = 0.3

        # Level 1: Try with grade filter
        docs = await self.retrieve(
            query=query,
            top_k=top_k,
            grade=grade,
            subject=subject,  # Passed through but not applied in retrieve()
        )
        docs = self._filter_by_score(docs, min_score)
        docs = self._deduplicate(docs)

        if len(docs) >= min_results:
            logger.debug("Grade filter returned %d docs", len(docs))
            return docs

        # Level 2: No filters (last resort)
        if grade:
            logger.info(
                "Fallback: removing all filters for '%s...'",
                query[:50],
            )
            docs = await self.retrieve(
                query=query,
                top_k=top_k,
                grade=None,
                subject=None,
            )
            # Lower threshold for fallback
            fallback_threshold = min_score * 0.5
            docs = self._filter_by_score(docs, fallback_threshold)
            docs = self._deduplicate(docs)

            for doc in docs:
                doc.setdefault("metadata", {})["fallback_level"] = 1

        return docs

    def _filter_by_score(self, docs: list[dict], min_score: float) -> list[dict]:
        """Filter documents by minimum score.

        Args:
            docs: Documents with scores
            min_score: Minimum acceptable score

        Returns:
            Filtered documents
        """
        return [d for d in docs if float(d.get("score", 0)) >= min_score]

    def _deduplicate(self, docs: list[dict]) -> list[dict]:
        """Remove near-duplicate results.

        Uses the first 200 characters of content as a fingerprint.
        Keeps the highest-scored version (docs must be pre-sorted by score).

        This catches duplicates from:
        - Overlapping text splitter fragments
        - Any parent chunks that slip through filters

        Args:
            docs: Documents sorted by score (highest first)

        Returns:
            Deduplicated documents
        """
        seen: set[str] = set()
        unique = []
        for doc in docs:
            fingerprint = doc.get("content", "").strip()[:200]
            if fingerprint in seen:
                logger.debug("Skipping duplicate chunk: %s...", fingerprint[:60])
                continue
            seen.add(fingerprint)
            unique.append(doc)
        return unique

    async def retrieve_for_context(
        self,
        query: str,
        grade: str,
        subject: str,
        max_tokens: int = 4000,
        use_fallback: bool = True,
    ) -> tuple[list[dict], str]:
        """Retrieve and format documents for LLM context.

        Retrieves relevant document chunks and formats them with source headers.

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter (reserved for future use)
            max_tokens: Maximum tokens for context window
            use_fallback: Whether to use fallback strategy

        Returns:
            Tuple of (documents, formatted_context_string)
        """
        # Input validation
        if not query or not query.strip():
            logger.warning("Empty query in retrieve_for_context")
            return [], ""

        if not grade:
            logger.warning("Missing grade: grade=%s", grade)

        if max_tokens < 100:
            logger.warning("max_tokens=%d too small, using 1000", max_tokens)
            max_tokens = 1000

        if max_tokens > 32000:
            logger.warning("max_tokens=%d too large, capping at 32000", max_tokens)
            max_tokens = 32000

        # Retrieve documents (already ranked by relevance)
        if use_fallback:
            docs = await self.retrieve_with_fallback(
                query=query,
                grade=grade,
                subject=subject,
            )
        else:
            docs = await self.retrieve(
                query=query,
                top_k=8,
                grade=grade,
                subject=subject,
            )

        if not docs:
            logger.warning("No documents retrieved for query: %s...", query[:50])
            return [], ""

        # Format context with source references
        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough char-to-token ratio

        for i, doc in enumerate(docs):
            metadata = doc.get("metadata", {})
            title = metadata.get("title", "Unknown Source")
            page_start = metadata.get("page_start", "?")
            page_end = metadata.get("page_end", page_start)
            section_title = metadata.get("section_title")

            # Build source header
            if page_start == page_end:
                page_ref = f"Page {page_start}"
            else:
                page_ref = f"Pages {page_start}-{page_end}"

            source_header = f"[{title}, {page_ref}]"
            if section_title:
                source_header += f" (Section: {section_title})"

            # Format chunk with header
            content = doc.get("content", "").strip()
            if not content:
                logger.warning("Empty content in doc %d, skipping", i)
                continue

            chunk = f"{source_header}\n{content}\n"

            # Check token limit
            if total_chars + len(chunk) > char_limit:
                logger.debug(
                    "Context limit reached: %d chars, stopping at doc %d/%d",
                    total_chars,
                    i,
                    len(docs),
                )
                break

            context_parts.append(chunk)
            total_chars += len(chunk)

        logger.info(
            "Context built: %d chunks, %d chars (~%d tokens)",
            len(context_parts),
            total_chars,
            total_chars // 4,
        )

        # Return only the docs that were included in context
        included_docs = docs[: len(context_parts)]
        formatted_context = "\n---\n".join(context_parts)

        return included_docs, formatted_context

    async def health_check(self) -> dict:
        """Check retriever health.

        Returns:
            Health status dict
        """
        try:
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
