"""RAG retriever with hybrid search, metadata filtering, and fallback strategies.

Retrieves relevant curriculum documents based on query, grade, and subject.
Uses Decimal for precise score handling in critical comparisons.
"""

from __future__ import annotations

import logging
import time
import asyncio
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
        self._hybrid_retriever = None

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

    def adaptive_cutoff(self, docs: list[dict], score_drop_threshold: float = 0.1) -> list[dict]:
        """Apply adaptive cutoff based on score drop.
        
        Args:
            docs: Documents with scores
            score_drop_threshold: Minimum score drop to trigger cutoff
            
        Returns:
            Filtered documents
        """
        if not docs or len(docs) <= 3:
            return docs
            
        cutoff_idx = len(docs)
        for i in range(len(docs) - 1):
            curr_score = docs[i].get("score", 0)
            next_score = docs[i + 1].get("score", 0)
            
            if curr_score - next_score > score_drop_threshold:
                cutoff_idx = i + 1
                break
                
        logger.debug(f"Adaptive cutoff: {len(docs)} → {cutoff_idx} docs")
        return docs[:cutoff_idx]

    async def retrieve(
        self,
        query: str,
        dense_query: str | None = None,
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
            # Use dense_query if provided (HyDE), otherwise use original query
            search_query_text = dense_query if dense_query else query
            
            # Use QdrantStore directly (Dense Retrieval)
            # We removed HybridRetriever because BM25 index was not being built/persisted,
            # making it a broken implementation.
            # Production Fix: Rely on robust Dense Retrieval for now.
            docs = await self.store.search(
                query=search_query_text,
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
                    "mode": "dense",
                },
            )

            return docs

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    async def retrieve_with_fallback(
        self,
        query: str,
        dense_query: str | None = None,
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
        docs = await self.retrieve(query, dense_query, top_k, grade, subject)
        docs = self._filter_by_score(docs, min_score)

        if len(docs) >= min_results:
            logger.debug(f"Exact filter returned {len(docs)} docs")
            return docs

        # Level 2: Try grade only (remove subject filter)
        if subject:
            logger.info(f"Fallback: removing subject filter for '{query[:50]}...'")
            docs = await self.retrieve(query, dense_query, top_k, grade, None)
            # Relax score slightly for cross-subject search
            docs = self._filter_by_score(docs, min_score * Decimal("0.8"))

            if len(docs) >= min_results:
                for doc in docs:
                    doc.setdefault("metadata", {})["fallback_level"] = 1
                return docs

        # Level 3: No filters (last resort)
        if grade:
            logger.info(f"Fallback: removing all filters for '{query[:50]}...'")
            docs = await self.retrieve(query, dense_query, top_k, None, None)
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
        return [d for d in docs if Decimal(str(d.get("score", 0))) >= min_score]

    async def retrieve_for_context(
        self,
        query: str,
        grade: str,
        subject: str,
        dense_query: str | None = None,
        max_tokens: int = 4000,
        use_fallback: bool = True,
    ) -> tuple[list[dict], str]:
        """Retrieve and format documents for LLM context.

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter
            dense_query: Optional transformed query (HyDE)
            max_tokens: Maximum tokens for context
            use_fallback: Whether to use fallback strategy

        Returns:
            Tuple of (documents, formatted_context_string)
        """
        if use_fallback:
            docs = await self.retrieve_with_fallback(
                query=query,
                dense_query=dense_query,
                grade=grade,
                subject=subject,
            )
        else:
            docs = await self.retrieve(
                query=query,
                dense_query=dense_query,
                top_k=15,
                grade=grade,
                subject=subject,
            )

        # Format context with source references
        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough char-to-token ratio

        # PARENT DOCUMENT RETRIEVAL
        # Fetch full context parents if available
        parent_ids = set()
        final_docs_map = {} # id -> doc
        
        # First pass: Identify parents and standalone docs
        for doc in docs:
            pid = doc['metadata'].get('parent_id')
            if pid:
                parent_ids.add(pid)
            elif doc.get('id'): # Check if it's already a parent or standalone
                 final_docs_map[doc['id']] = doc
            else:
                # Fallback for docs without ID (unlikely)
                final_docs_map[f"temp_{hash(doc['content'])}"] = doc

        # Fetch parents
        if parent_ids:
            try:
                parent_docs = await self.store.get_by_ids(list(parent_ids))
                for p_doc in parent_docs:
                    final_docs_map[p_doc['id']] = p_doc
                    
                logger.debug(f"Retrieved {len(parent_docs)} parent documents for context expansion")
            except Exception as e:
                logger.warning(f"Failed to fetch parent documents: {e}")
                # Fallback: keep original child docs if parent fetch fails
                pass
        
        # If we failed to get any parents, or if we have children without parents fetched
        # We need to make sure we don't lose the original docs content
        # Strategy: Use Parent if fetched, else use Child
        
        # Re-construct final list ensuring we have content
        # Note: If multiple children point to same parent, parent is only added once in final_docs_map
        
        unique_docs = list(final_docs_map.values())
        
        # If unique_docs is empty (e.g. only children and parent fetch failed), fallback to original docs
        if not unique_docs and docs:
             unique_docs = docs
        elif not unique_docs: # No docs at all
             unique_docs = []

        # Sort by score if available? Parents don't have search scores (default 1.0)
        # Original docs had scores. We lose ranking here.
        # But context order matters less for powerful models, usually just relevance.
        # We could try to map Child Score -> Parent Score (Max aggregation)
        
        # Simple heuristic: Keep original order of appearance?
        # Difficult because 5 children -> 1 Parent.
        
        # Just use the fetched unique docs
        
        for doc in unique_docs:
            if 'title' not in doc['metadata']:
                logger.warning(f"Document chunk {doc.get('id', 'unknown')} missing 'title' metadata.")
            
            title = doc['metadata'].get('title', 'Source')
            page = doc['metadata'].get('page_start', '?')
            # Use 'section_title' if available for better context
            section = doc['metadata'].get('section_title')
            source_header = f"[{title}, Page {page}]"
            if section:
                source_header += f" (Section: {section})"
                
            chunk = f"{source_header}\n{doc['content']}\n"

            if total_chars + len(chunk) > char_limit:
                break

            context_parts.append(chunk)
            total_chars += len(chunk)

        # Return unique_docs (containing Parents) so generator uses THEM for citations
        return unique_docs, "\n---\n".join(context_parts)

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
