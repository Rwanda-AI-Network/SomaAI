"""RAG reranker for relevance scoring.

MVP: Reranking is disabled to avoid heavy PyTorch dependencies.
The fallback returns documents in their original retrieval order.
Uses Decimal for precise score handling.

TODO (Post-MVP): Enable cross-encoder reranking by:
1. Uncomment sentence-transformers in pyproject.toml
2. Uncomment the model loading code below
3. Or implement a lightweight API-based alternative (Cohere, Jina, etc.)
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Singleton instance
_RERANKER_INSTANCE: Reranker | None = None


def get_reranker() -> Reranker:
    """Get singleton reranker instance.

    Avoids reloading the model on each request.

    Returns:
        Reranker instance
    """
    global _RERANKER_INSTANCE
    if _RERANKER_INSTANCE is None:
        _RERANKER_INSTANCE = Reranker()
    return _RERANKER_INSTANCE


class Reranker:
    """Cross-encoder reranker for improved relevance.

    MVP Status: DISABLED
    - Returns documents in original retrieval order with simulated scores
    - Saves ~3.5GB in Docker image size (no PyTorch/CUDA)

    Post-MVP: Uncomment model loading to enable cross-encoder reranking.
    """

    def __init__(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> None:
        """Initialize reranker.

        Args:
            model_name: HuggingFace cross-encoder model name
        """
        self.model_name = model_name
        self._model = None
        self._load_attempted = False

    @property
    def model(self):
        """Lazy-load cross-encoder model.

        MVP: Model loading is disabled to avoid PyTorch dependency.
        """
        # =========================================================
        # TODO (Post-MVP): Uncomment to enable cross-encoder reranking
        # =========================================================
        # if self._model is None and not self._load_attempted:
        #     self._load_attempted = True
        #     try:
        #         from sentence_transformers import CrossEncoder
        #         logger.info(f"Loading reranker model: {self.model_name}")
        #         self._model = CrossEncoder(self.model_name)
        #         logger.info("Reranker model loaded successfully")
        #     except ImportError:
        #         logger.warning(
        #             "sentence-transformers not installed. "
        #             "Reranking disabled. Install with: uv add sentence-transformers"
        #         )
        #     except Exception as e:
        #         logger.error(f"Failed to load reranker model: {e}")
        # =========================================================

        # MVP: Always return None (disabled)
        if not self._load_attempted:
            self._load_attempted = True
            logger.info("Reranker disabled for MVP - using retrieval order")
        return self._model

    @property
    def is_available(self) -> bool:
        """Check if reranker model is available.

        MVP: Always returns False (reranking disabled).
        """
        return self.model is not None

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
        min_score: Decimal | None = None,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        MVP: Returns documents in original order with simulated scores.
        Post-MVP: Will use cross-encoder for actual relevance scoring.
        Uses Decimal for precise score handling.

        Args:
            query: User's question
            documents: List of docs with 'content' key
            top_k: Number of top results to return
            min_score: Optional minimum score threshold (Decimal)

        Returns:
            Reranked documents sorted by relevance score
        """
        if not documents:
            return []

        # MVP: Reranking disabled - return original order with simulated scores
        # This uses the retrieval order which is already ranked by embedding similarity
        if not self.is_available:
            logger.debug("Reranker disabled (MVP) - using retrieval order")
            for i, doc in enumerate(documents):
                # Use retrieval score if available, otherwise simulate
                # Convert to Decimal for precise handling
                if "score" in doc:
                    doc["rerank_score"] = Decimal(str(doc["score"]))
                else:
                    doc["rerank_score"] = Decimal("1.0") - (
                        Decimal(str(i)) * Decimal("0.01")
                    )
            return documents[:top_k]

        # =========================================================
        # TODO (Post-MVP): Uncomment to enable cross-encoder reranking
        # =========================================================
        # # Create query-document pairs
        # pairs = [(query, doc.get("content", "")) for doc in documents]
        #
        # # Score pairs with cross-encoder
        # try:
        #     scores = self.model.predict(pairs)
        # except Exception as e:
        #     logger.error(f"Reranking failed: {e}")
        #     return documents[:top_k]
        #
        # # Add scores to documents
        # for doc, score in zip(documents, scores):
        #     doc["rerank_score"] = float(score)
        #
        # # Filter by minimum score if specified
        # if min_score is not None:
        #     documents = [
        #         d for d in documents if d.get("rerank_score", 0) >= min_score
        #     ]
        #
        # # Sort by score and return top-k
        # sorted_docs = sorted(
        #     documents,
        #     key=lambda x: x.get("rerank_score", 0),
        #     reverse=True,
        # )
        #
        # logger.debug(
        #     f"Reranked {len(documents)} docs, "
        #     f"top score: {sorted_docs[0]['rerank_score']:.3f}"
        #     if sorted_docs
        #     else "no docs",
        # )
        #
        # return sorted_docs[:top_k]
        # =========================================================

        return documents[:top_k]


# Module-level function for backward compatibility
async def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank documents based on the query.

    Args:
        query: Search query
        documents: Retrieved documents
        top_k: Number of results to return

    Returns:
        Reranked documents
    """
    reranker = get_reranker()
    return await reranker.rerank(query, documents, top_k)
