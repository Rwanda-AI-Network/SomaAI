"""Qdrant vector store implementation using LangChain.

Provides semantic search with metadata filtering for grade and subject.
Includes content hashing for deduplication and connection pooling.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from somaai.modules.knowledge.vectorstore import VectorStore
from somaai.utils.files import compute_file_hash
from somaai.utils.retry import retry_async

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)

# Singleton client for connection pooling
_QDRANT_CLIENT: QdrantClient | None = None
_EMBEDDINGS_MODEL: HuggingFaceEmbeddings | OpenAIEmbeddings | None = None


def get_qdrant_client(settings: Settings) -> QdrantClient:
    """Get singleton Qdrant client (connection pooling).

    Args:
        settings: Application settings

    Returns:
        Shared QdrantClient instance
    """
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        logger.info(f"Creating Qdrant client: {settings.qdrant_url}")
        _QDRANT_CLIENT = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=30,
        )
    return _QDRANT_CLIENT


def get_embeddings_model(settings: Settings) -> HuggingFaceEmbeddings | OpenAIEmbeddings:
    """Get singleton embeddings model.

    Args:
        settings: Application settings

    Returns:
        Shared Embeddings instance
    """
    global _EMBEDDINGS_MODEL
    if _EMBEDDINGS_MODEL is None:
        if settings.openai_api_key:
            logger.info("Creating OpenAI embeddings model")
            _EMBEDDINGS_MODEL = OpenAIEmbeddings(
                api_key=settings.openai_api_key,
                model="text-embedding-3-small",
            )
        else:
            logger.info("Creating HuggingFace embeddings model (local)")
            _EMBEDDINGS_MODEL = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
    return _EMBEDDINGS_MODEL


class QdrantStore(VectorStore):
    """Qdrant vector store with LangChain integration.

    Features:
    - Connection pooling (singleton client)
    - Batch deduplication (O(1) per batch)
    - Retry logic for embeddings
    - Metadata filtering (grade, subject)
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize Qdrant store.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._store: QdrantVectorStore | None = None

    @property
    def client(self) -> QdrantClient:
        """Get singleton Qdrant client."""
        return get_qdrant_client(self.settings)

    @property
    def embeddings(self) -> HuggingFaceEmbeddings | OpenAIEmbeddings:
        """Get singleton embeddings model."""
        return get_embeddings_model(self.settings)

    @property
    def store(self) -> QdrantVectorStore:
        """Get vector store."""
        if self._store is None:
            collection_name = self.settings.qdrant_collection_name

            # Ensure collection exists
            if not self.client.collection_exists(collection_name):
                logger.info(f"Collection {collection_name} not found, creating...")

                # Determine dimension dynamically
                try:
                    # Generate a dummy embedding to get dimension
                    sample_embedding = self.embeddings.embed_query("test")
                    dimension = len(sample_embedding)
                    logger.info(f"Detected embedding dimension: {dimension}")

                    from qdrant_client.models import Distance, VectorParams
                    self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=dimension,
                            distance=Distance.COSINE
                        )
                    )
                    logger.info(f"Created collection {collection_name}")
                except Exception as e:
                    logger.error(f"Failed to create collection: {e}")
                    # Let downstream fail if needed

            self._store = QdrantVectorStore(
                client=self.client,
                collection_name=collection_name,
                embedding=self.embeddings,
            )
        return self._store

    async def add(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadata: list[dict] | None = None,
        skip_duplicates: bool = True,
    ) -> list[str]:
        """Add documents with batch deduplication.

        Uses batch hash lookup (O(1) per batch) instead of O(n).

        Args:
            texts: Document texts
            embeddings: Pre-computed embeddings (ignored)
            metadata: Document metadata
            skip_duplicates: Skip existing chunks

        Returns:
            List of added document IDs
        """
        from langchain_core.documents import Document

        metadata_list = metadata or [{}] * len(texts)

        # Compute all hashes first
        hashes = [compute_file_hash(t.encode("utf-8")) for t in texts]

        # Batch check for existing hashes (O(1) instead of O(n))
        if skip_duplicates:
            existing = await self._batch_check_hashes(hashes)
        else:
            existing = set()

        # Filter to non-duplicate docs
        docs_to_add = []
        for text, meta, content_hash in zip(texts, metadata_list, hashes):
            if content_hash in existing:
                logger.debug(f"Skipping duplicate chunk: {content_hash[:16]}...")
                continue

            meta["content_hash"] = content_hash
            docs_to_add.append(Document(page_content=text, metadata=meta))

        if not docs_to_add:
            logger.info("All chunks were duplicates, nothing to add")
            return []

        # Add with retry logic
        logger.info(f"Adding {len(docs_to_add)} chunks to Qdrant")
        ids = await self._add_with_retry(docs_to_add)
        return ids

    @retry_async(max_attempts=3, base_delay=2.0)
    async def _add_with_retry(self, docs: list) -> list[str]:
        """Add documents with retry on failure.

        Args:
            docs: LangChain documents

        Returns:
            Document IDs
        """
        return await self.store.aadd_documents(docs)

    async def _batch_check_hashes(self, hashes: list[str]) -> set[str]:
        """Batch check which hashes already exist.

        Single query instead of O(n) queries.

        Args:
            hashes: List of content hashes

        Returns:
            Set of existing hashes
        """
        if not hashes:
            return set()

        try:
            # Use should filter with multiple OR conditions
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            results = self.client.scroll(
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    should=[
                        FieldCondition(
                            key="content_hash",
                            match=MatchAny(any=hashes[:100]),  # Qdrant limit
                        )
                    ]
                ),
                limit=len(hashes),
                with_payload=["content_hash"],
            )

            existing = {
                p.payload.get("content_hash")
                for p in results[0]
                if p.payload and p.payload.get("content_hash")
            }
            logger.debug(f"Found {len(existing)} existing hashes out of {len(hashes)}")
            return existing

        except Exception as e:
            logger.warning(f"Batch hash check failed: {e}, falling back to empty set")
            return set()

    async def exists_by_hash(self, content_hash: str) -> bool:
        """Check if chunk exists by hash.

        Args:
            content_hash: SHA-256 hash

        Returns:
            True if exists
        """
        existing = await self._batch_check_hashes([content_hash])
        return content_hash in existing

    async def exists_by_doc_id(self, doc_id: str) -> bool:
        """Check if document has chunks.

        Args:
            doc_id: Document ID

        Returns:
            True if chunks exist
        """
        try:
            results = self.client.scroll(
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=1,
            )
            return len(results[0]) > 0
        except Exception:
            return False

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_id: Document ID

        Returns:
            Number deleted
        """
        try:
            results = self.client.scroll(
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=10000,
                with_payload=False,
            )
            point_ids = [p.id for p in results[0]]

            if point_ids:
                self.client.delete(
                    collection_name=self.settings.qdrant_collection_name,
                    points_selector=point_ids,
                )

            return len(point_ids)
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0

    async def search(
        self,
        query: str,
        top_k: int = 10,
        grade: str | None = None,
        subject: str | None = None,
    ) -> list[dict]:
        """Search for similar documents.

        Args:
            query: Search query
            top_k: Number of results
            grade: Grade filter
            subject: Subject filter

        Returns:
            List of documents with scores
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must_conditions = []
        if grade:
            must_conditions.append(
                FieldCondition(key="grade", match=MatchValue(value=grade))
            )
        if subject:
            must_conditions.append(
                FieldCondition(key="subject", match=MatchValue(value=subject))
            )

        qdrant_filter = Filter(must=must_conditions) if must_conditions else None

        docs = await self.store.asimilarity_search_with_score(
            query,
            k=top_k,
            filter=qdrant_filter,
        )

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in docs
        ]

    async def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""
        await self.store.adelete(ids)

    async def search_embedding(
        self,
        embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Search by embedding vector."""
        docs = await self.store.asimilarity_search_by_vector(embedding, k=top_k)
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]
