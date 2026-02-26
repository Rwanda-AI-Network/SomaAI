"""RAG reranker for relevance scoring.

Uses a Cross-Encoder model to improve retrieval accuracy by re-scoring
candidate documents based on their relevance to the query.

Dependencies:
- sentence-transformers (for CrossEncoder)
- PyTorch (backend)
"""

from __future__ import annotations

import asyncio
import logging

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

    Uses a HuggingFace Cross-Encoder model to score query-document pairs.
    Falls back to original retrieval order if the model cannot be loaded.
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
        if self._model is None and not self._load_attempted:
            self._load_attempted = True
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"Loading reranker model: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
                logger.info("Reranker model loaded successfully")
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed. "
                    "Reranking disabled. Install with: uv add sentence-transformers"
                )
            except Exception as e:
                logger.error(f"Failed to load reranker model: {e}")

        return self._model

    @property
    def is_available(self) -> bool:
        """Check if reranker model is available."""
        return self.model is not None

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
        min_score: float | None = None,
    ) -> list[dict]:
        """Rerank documents by relevance to query.

        Uses Cross-Encoder for precise relevance scoring.
        Returns top_k documents sorted by score.

        Args:
            query: User's question
            documents: List of docs with 'content' key
            top_k: Number of top results to return
            min_score: Optional minimum score threshold

        Returns:
            Reranked documents sorted by relevance score
        """
        if not documents:
            return []

        # If model unavailable, return original order with retrieval scores
        if not self.is_available:
            logger.debug("Reranker unavailable - using retrieval order")
            for i, doc in enumerate(documents):
                if "score" in doc:
                    doc["rerank_score"] = float(doc["score"])
                else:
                    doc["rerank_score"] = 1.0 - (i * 0.01)
            return documents[:top_k]

        # Create query-document pairs
        pairs = [(query, doc.get("content", "")) for doc in documents]

        # Score pairs with cross-encoder (offload to thread pool to avoid blocking)
        try:
            loop = asyncio.get_running_loop()
            scores = await loop.run_in_executor(None, self.model.predict, pairs)
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return documents[:top_k]

        # Add scores to documents
        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        # Filter by minimum score if specified
        if min_score is not None:
            documents = [d for d in documents if d.get("rerank_score", 0) >= min_score]

        # Sort by score and return top-k
        sorted_docs = sorted(
            documents,
            key=lambda x: x.get("rerank_score", 0),
            reverse=True,
        )

        logger.debug(
            f"Reranked {len(documents)} docs, "
            f"top score: {sorted_docs[0]['rerank_score']:.3f}"
            if sorted_docs
            else "no docs",
        )

        return sorted_docs[:top_k]
