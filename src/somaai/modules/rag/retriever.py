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


def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[tuple[str, float]],
    k: int = 60,
    alpha: float = 0.5
) -> list[dict]:
    """Combine dense and sparse results using Reciprocal Rank Fusion.
    
    RRF Formula: score(d) = Σ(1 / (k + rank_i(d)))
    
    Args:
        dense_results: Results from dense retrieval (Qdrant)
        sparse_results: Results from sparse retrieval (BM25) as (doc_id, score)
        k: RRF constant (default: 60, standard value)
        alpha: Weight for dense vs sparse (0=sparse only, 0.5=balanced, 1=dense only)
        
    Returns:
        Fused results sorted by combined score with normalized scores
        
    Example:
        >>> dense = [{'metadata': {'chunk_id': 'doc1'}, 'score': 0.9}]
        >>> sparse = [('doc1', 15.2), ('doc2', 12.1)]
        >>> fused = reciprocal_rank_fusion(dense, sparse, k=60, alpha=0.5)
    """
    scores = {}
    doc_map = {}
    
    # Dense scores (weighted by alpha)
    for rank, doc in enumerate(dense_results):
        doc_id = doc['metadata'].get('chunk_id', doc['metadata'].get('doc_id'))
        if not doc_id:
            continue
        rrf_score = alpha / (k + rank + 1)
        scores[doc_id] = scores.get(doc_id, 0) + rrf_score
        doc_map[doc_id] = doc
    
    # Sparse scores (weighted by 1-alpha)
    for rank, (doc_id, _) in enumerate(sparse_results):
        rrf_score = (1 - alpha) / (k + rank + 1)
        scores[doc_id] = scores.get(doc_id, 0) + rrf_score
        # If doc not in dense results, we skip it (need full doc object)
    
    # Sort by combined score
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_ids:
        return []
    
    # CRITICAL FIX: Normalize RRF scores to [0, 1] range
    # This fixes Bug #1 where RRF scores (~0.01-0.03) were incompatible with
    # downstream score thresholds that expect [0, 1] range
    max_score = sorted_ids[0][1]
    min_score = sorted_ids[-1][1] if len(sorted_ids) > 1 else 0
    score_range = max_score - min_score if max_score > min_score else 1.0
    
    # Build result list with normalized scores
    results = []
    for doc_id, rrf_score in sorted_ids:
        if doc_id in doc_map:
            doc = doc_map[doc_id].copy()
            # Normalize to [0, 1] range for compatibility with thresholds
            normalized_score = (rrf_score - min_score) / score_range if score_range > 0 else rrf_score
            doc['rrf_score_raw'] = rrf_score  # Keep original for debugging
            doc['score'] = normalized_score  # Use normalized for downstream
            results.append(doc)
    
    return results


class Retriever:
    """Document retriever with dense semantic search and metadata filtering.

    Uses Qdrant vector store with cosine similarity for semantic search.
    Supports metadata filtering by grade level and subject.
    Implements 3-level fallback strategy when filters return insufficient results.
    
    Fallback Strategy:
        Level 1: grade + subject filters
        Level 2: grade only (if <3 results)
        Level 3: no filters (if still <3 results)
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
        hyde_query: str | None = None,
        top_k: int = 15,
        grade: str | None = None,
        subject: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant documents.

        Args:
            query: User's question
            hyde_query: HyDE-transformed query (if HyDE is enabled)
            top_k: Number of documents to retrieve
            grade: Filter by grade level (e.g., "S1", "P6")
            subject: Filter by subject (e.g., "mathematics")

        Returns:
            List of documents with content, metadata, and scores
        """
        # Input validation (can be disabled via settings)
        if getattr(self.settings, 'rag_enable_input_validation', True):
            if not query or not query.strip():
                logger.warning("Empty query provided to retriever")
                return []
            
            if top_k < 1:
                logger.warning(f"Invalid top_k={top_k}, using default 15")
                top_k = 15
            
            if top_k > 100:
                logger.warning(f"top_k={top_k} exceeds maximum, capping at 100")
                top_k = 100
            
            # Sanitize query
            query = query.strip()
            if hyde_query:
                hyde_query = hyde_query.strip()
        
        start_time = time.time()

        try:
            # Use HyDE query if provided, otherwise use original query
            search_query_text = hyde_query if hyde_query else query
            
            # Determine top_k for retrieval
            # If hybrid search enabled, retrieve more for better fusion
            retrieval_top_k = top_k * 2 if getattr(self.settings, 'rag_enable_hybrid_search', False) else top_k
            
            # Dense retrieval using Qdrant vector store
            # Uses cosine similarity on normalized embeddings
            dense_docs = await self.store.search(
                query=search_query_text,
                top_k=retrieval_top_k,
                grade=grade,
                subject=subject,
            )
            
            # Hybrid search if enabled
            if getattr(self.settings, 'rag_enable_hybrid_search', False):
                try:
                    from somaai.modules.knowledge.bm25_index import get_bm25_index
                    
                    bm25_index = get_bm25_index(self.settings)
                    
                    # Check if index has documents
                    if bm25_index.size() > 0:
                        # Sparse retrieval using BM25
                        sparse_results = bm25_index.search(query, top_k=retrieval_top_k)
                        
                        # Fuse results using RRF
                        docs = reciprocal_rank_fusion(
                            dense_results=dense_docs,
                            sparse_results=sparse_results,
                            k=60,
                            alpha=self.settings.rag_hybrid_alpha
                        )[:top_k]
                        
                        logger.info(
                            f"Hybrid search: {len(dense_docs)} dense + "
                            f"{len(sparse_results)} sparse → {len(docs)} fused"
                        )
                    else:
                        logger.warning("BM25 index is empty, using dense only")
                        docs = dense_docs[:top_k]
                        
                except ImportError:
                    logger.warning("BM25 not available (rank-bm25 not installed), using dense only")
                    docs = dense_docs[:top_k]
                except Exception as e:
                    logger.warning(f"Hybrid search failed: {e}, falling back to dense only")
                    docs = dense_docs[:top_k]
            else:
                docs = dense_docs[:top_k]

            # Log retrieval metrics
            latency_ms = (time.time() - start_time) * 1000
            top_score = docs[0].get("score", 0) if docs else 0
            mode = "hybrid" if getattr(self.settings, 'rag_enable_hybrid_search', False) else "dense"

            logger.info(
                "retrieval",
                extra={
                    "query_length": len(query),
                    "docs_returned": len(docs),
                    "top_score": top_score,
                    "latency_ms": latency_ms,
                    "grade": grade,
                    "subject": subject,
                    "mode": mode,
                },
            )

            return docs

        except ConnectionError as e:
            logger.error(f"Qdrant connection failed: {e}")
            return []
        
        except TimeoutError as e:
            logger.error(f"Qdrant request timeout: {e}")
            return []
        
        except ValueError as e:
            logger.error(f"Invalid parameters for retrieval: {e}")
            return []
        
        except Exception as e:
            logger.error(f"Retrieval failed with unexpected error: {e}", exc_info=True)
            return []

    async def retrieve_with_fallback(
        self,
        query: str,
        hyde_query: str | None = None,
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
            hyde_query: HyDE-transformed query (if HyDE is enabled)
            grade: Grade level filter
            subject: Subject filter
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
        
        if min_results < 1:
            logger.warning(f"Invalid min_results={min_results}, using default 3")
            min_results = 3
        
        if min_score < Decimal("0.0") or min_score > Decimal("1.0"):
            logger.warning(f"Invalid min_score={min_score}, using default 0.3")
            min_score = Decimal("0.3")
        
        # Level 1: Try exact filters
        docs = await self.retrieve(
            query=query,
            hyde_query=hyde_query,
            top_k=top_k,
            grade=grade,
            subject=subject,
        )
        docs = self._filter_by_score(docs, min_score)

        if len(docs) >= min_results:
            logger.debug(f"Exact filter returned {len(docs)} docs")
            return docs

        # Level 2: Try grade only (remove subject filter)
        if subject:
            logger.info(f"Fallback: removing subject filter for '{query[:50]}...'")
            docs = await self.retrieve(
                query=query,
                hyde_query=hyde_query,
                top_k=top_k,
                grade=grade,
                subject=None,
            )
            # Relax score slightly for cross-subject search
            docs = self._filter_by_score(docs, min_score * Decimal("0.8"))

            if len(docs) >= min_results:
                for doc in docs:
                    doc.setdefault("metadata", {})["fallback_level"] = 1
                return docs

        # Level 3: No filters (last resort)
        if grade:
            logger.info(f"Fallback: removing all filters for '{query[:50]}...'")
            docs = await self.retrieve(
                query=query,
                hyde_query=hyde_query,
                top_k=top_k,
                grade=None,
                subject=None,
            )
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
        hyde_query: str | None = None,
        max_tokens: int = 4000,
        use_fallback: bool = True,
    ) -> tuple[list[dict], str]:
        """Retrieve and format documents for LLM context.

        Retrieves relevant document chunks and formats them with source headers.
        Uses child chunks directly (which already have section context from semantic chunker).

        Args:
            query: User's question
            grade: Grade level filter
            subject: Subject filter
            hyde_query: HyDE-transformed query (if HyDE is enabled)
            max_tokens: Maximum tokens for context window
            use_fallback: Whether to use fallback strategy

        Returns:
            Tuple of (documents, formatted_context_string)
            - documents: List of retrieved docs with metadata and scores
            - formatted_context_string: Formatted text for LLM prompt
        """
        # Input validation
        if not query or not query.strip():
            logger.warning("Empty query in retrieve_for_context")
            return [], ""
        
        if not grade or not subject:
            logger.warning(f"Missing grade or subject: grade={grade}, subject={subject}")
            # Continue anyway - fallback will handle it
        
        if max_tokens < 100:
            logger.warning(f"max_tokens={max_tokens} too small, using 1000")
            max_tokens = 1000
        
        if max_tokens > 32000:
            logger.warning(f"max_tokens={max_tokens} too large, capping at 32000")
            max_tokens = 32000
        
        # Retrieve documents (already ranked by relevance)
        if use_fallback:
            docs = await self.retrieve_with_fallback(
                query=query,
                hyde_query=hyde_query,
                grade=grade,
                subject=subject,
            )
        else:
            docs = await self.retrieve(
                query=query,
                hyde_query=hyde_query,
                top_k=15,
                grade=grade,
                subject=subject,
            )

        if not docs:
            logger.warning(f"No documents retrieved for query: {query[:50]}...")
            return [], ""

        # Format context with source references
        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough char-to-token ratio (1 token ≈ 4 chars)

        for i, doc in enumerate(docs):
            # Extract metadata safely
            metadata = doc.get('metadata', {})
            title = metadata.get('title', 'Unknown Source')
            page_start = metadata.get('page_start', '?')
            page_end = metadata.get('page_end', page_start)
            section_title = metadata.get('section_title')
            
            # Build source header
            if page_start == page_end:
                page_ref = f"Page {page_start}"
            else:
                page_ref = f"Pages {page_start}-{page_end}"
            
            source_header = f"[{title}, {page_ref}]"
            if section_title:
                source_header += f" (Section: {section_title})"
            
            # Format chunk with header
            content = doc.get('content', '').strip()
            if not content:
                logger.warning(f"Empty content in doc {i}, skipping")
                continue
                
            chunk = f"{source_header}\n{content}\n"

            # Check token limit
            if total_chars + len(chunk) > char_limit:
                logger.debug(
                    f"Context limit reached: {total_chars} chars, "
                    f"stopping at doc {i}/{len(docs)}"
                )
                break

            context_parts.append(chunk)
            total_chars += len(chunk)

        logger.info(
            f"Context built: {len(context_parts)} chunks, "
            f"{total_chars} chars (~{total_chars // 4} tokens)"
        )
        
        # Return only the docs that were included in context
        included_docs = docs[:len(context_parts)]
        formatted_context = "\n---\n".join(context_parts)
        
        return included_docs, formatted_context

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
