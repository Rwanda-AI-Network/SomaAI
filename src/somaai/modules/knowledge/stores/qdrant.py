"""Qdrant vector store implementation using LangChain.

Provides semantic search with metadata filtering for grade and subject.
Includes content hashing for deduplication and connection pooling.

IMPORTANT: LangChain's QdrantVectorStore stores documents with this payload structure:
    {
        "page_content": "...",
        "metadata": { "grade": "S6", "doc_id": "...", ... }
    }

All FieldCondition filters must use "metadata.<field>" to match nested keys.
The similarity_search_with_score method handles this automatically via its
internal _document_from_point, but raw client.scroll() calls do NOT.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from somaai.modules.knowledge.embeddings import get_embeddings
from somaai.modules.knowledge.vectorstore import VectorStore
from somaai.utils.files import compute_file_hash

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)

# Singleton client for connection pooling
_QDRANT_CLIENT: QdrantClient | None = None


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
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None
            ),
            timeout=30,
        )
    return _QDRANT_CLIENT


def close_qdrant_client() -> None:
    """Close the singleton Qdrant client.

    Call on application shutdown to release connections.
    """
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is not None:
        try:
            _QDRANT_CLIENT.close()
            logger.info("Qdrant client closed")
        except Exception as e:
            logger.warning("Error closing Qdrant client: %s", e)
        finally:
            _QDRANT_CLIENT = None


class QdrantStore(VectorStore):
    """Qdrant vector store with LangChain integration.

    Features:
    - Connection pooling (singleton client)
    - Batch deduplication (O(1) per batch)
    - Retry logic for embeddings
    - Metadata filtering (grade, subject)
    """

    # LangChain payload key prefix for metadata fields.
    # LangChain stores: {"page_content": "...", "metadata": {"grade": "S6", ...}}
    # Raw Qdrant filters need "metadata.grade" to reach nested fields.
    META_PREFIX = "metadata"

    def __init__(self, settings: Settings) -> None:
        """Initialize Qdrant store.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._store: QdrantVectorStore | None = None

    def _meta_key(self, field: str) -> str:
        """Build the full Qdrant payload key for a metadata field.

        LangChain nests document metadata under a "metadata" key in the
        Qdrant payload, so filtering on "grade" requires "metadata.grade".

        Args:
            field: Metadata field name (e.g., "grade", "doc_id")

        Returns:
            Fully qualified key (e.g., "metadata.grade")
        """
        return f"{self.META_PREFIX}.{field}"

    @property
    def client(self) -> QdrantClient:
        """Get singleton Qdrant client."""
        return get_qdrant_client(self.settings)

    @property
    def embeddings(self) -> HuggingFaceEmbeddings | OpenAIEmbeddings:
        """Get singleton embeddings model."""
        return get_embeddings(self.settings)

    async def _ensure_store(self) -> QdrantVectorStore:
        """Get or lazily initialise the vector store.

        Replaces the previous synchronous ``store`` property so that the
        blocking Qdrant ``collection_exists`` / ``create_collection`` calls
        and HuggingFace ``embed_query`` call are offloaded to a thread.
        """
        if self._store is not None:
            return self._store

        collection_name = self.settings.qdrant_collection_name

        # Ensure collection exists — sync I/O → thread
        exists = await asyncio.to_thread(
            self.client.collection_exists, collection_name
        )
        if not exists:
            logger.info(f"Collection {collection_name} not found, creating...")
            try:
                # Generate a dummy embedding to get dimension — CPU-bound
                sample_embedding = await asyncio.to_thread(
                    self.embeddings.embed_query, "test"
                )
                dimension = len(sample_embedding)
                logger.info(f"Detected embedding dimension: {dimension}")

                from qdrant_client.models import Distance, VectorParams

                await asyncio.to_thread(
                    self.client.create_collection,
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=dimension, distance=Distance.COSINE
                    ),
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

    async def as_retriever(self, search_kwargs: dict | None = None):
        """Get as LangChain retriever."""
        store = await self._ensure_store()
        return store.as_retriever(search_kwargs=search_kwargs or {})

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

        # Ensure store is initialised before adding
        await self._ensure_store()

        # Add with retry logic
        logger.info(f"Adding {len(docs_to_add)} chunks to Qdrant")
        ids = await self._add_with_retry(docs_to_add)
        return ids

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _add_with_retry(self, docs: list) -> list[str]:
        """Add documents with retry on failure.

        Uses tenacity for robust retry logic with exponential backoff.

        Args:
            docs: LangChain documents

        Returns:
            Document IDs
        """
        store = await self._ensure_store()
        return await store.aadd_documents(docs)

    async def _batch_check_hashes(self, hashes: list[str]) -> set[str]:
        """Batch check which hashes already exist.

        Paginates in batches of 100 to avoid Qdrant MatchAny limits
        while still checking ALL hashes (no silent truncation).

        Args:
            hashes: List of content hashes

        Returns:
            Set of existing hashes
        """
        if not hashes:
            return set()

        batch_size = 100
        existing: set[str] = set()

        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            for i in range(0, len(hashes), batch_size):
                batch = hashes[i : i + batch_size]

                results = await asyncio.to_thread(
                    self.client.scroll,
                    collection_name=self.settings.qdrant_collection_name,
                    scroll_filter=Filter(
                        should=[
                            FieldCondition(
                                key=self._meta_key("content_hash"),
                                match=MatchAny(any=batch),
                            )
                        ]
                    ),
                    limit=len(batch),
                    with_payload=[self._meta_key("content_hash")],
                )

                existing.update(
                    p.payload.get("metadata", {}).get("content_hash")
                    for p in results[0]
                    if p.payload and p.payload.get("metadata", {}).get("content_hash")
                )

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
            results = await asyncio.to_thread(
                self.client.scroll,
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key=self._meta_key("doc_id"),
                            match=MatchValue(value=doc_id),
                        )
                    ]
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
            results = await asyncio.to_thread(
                self.client.scroll,
                collection_name=self.settings.qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key=self._meta_key("doc_id"),
                            match=MatchValue(value=doc_id),
                        )
                    ]
                ),
                limit=10000,
                with_payload=False,
            )
            point_ids = [p.id for p in results[0]]

            if point_ids:
                await asyncio.to_thread(
                    self.client.delete,
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
        """Search for similar documents with metadata filtering.

        Note: LangChain's asimilarity_search_with_score passes the filter
        directly to qdrant_client.query_points(query_filter=filter).
        Since LangChain nests metadata under "metadata.*", filters must
        use "metadata.grade" not "grade".

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
                FieldCondition(
                    key=self._meta_key("grade"),
                    match=MatchValue(value=grade),
                )
            )
        if subject:
            must_conditions.append(
                FieldCondition(
                    key=self._meta_key("subject"),
                    match=MatchValue(value=subject),
                )
            )

        # Exclude parent chunks from search results.
        # Parent chunks (is_parent=True) are full-section copies kept for
        # ID-based lookup. They overlap with their child fragments and
        # produce duplicate results if included in similarity search.
        must_not_conditions = [
            FieldCondition(
                key=self._meta_key("is_parent"),
                match=MatchValue(value=True),
            )
        ]

        qdrant_filter = Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions,
        )

        store = await self._ensure_store()
        docs = await store.asimilarity_search_with_score(
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
        store = await self._ensure_store()
        await store.adelete(ids)

    async def search_embedding(
        self,
        embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Search by pre-computed embedding vector.

        Applies the same parent-chunk exclusion filter as ``search()``
        so callers never receive full-section parent duplicates regardless
        of which search path they use.
        """
        # Exclude parent chunks — mirrors the must_not condition in search()
        parent_exclusion = Filter(
            must_not=[
                FieldCondition(
                    key=self._meta_key("is_parent"),
                    match=MatchValue(value=True),
                )
            ]
        )
        store = await self._ensure_store()
        docs = await store.asimilarity_search_by_vector(
            embedding, k=top_k, filter=parent_exclusion
        )
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]

    async def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Retrieve documents by their IDs.

        Args:
            ids: List of chunk IDs

        Returns:
            List of documents with content and metadata
        """
        if not ids:
            return []

        try:
            points = await asyncio.to_thread(
                self.client.retrieve,
                collection_name=self.settings.qdrant_collection_name,
                ids=ids,
                with_payload=True,
                with_vectors=False,
            )

            results = []
            for point in points:
                if point.payload:
                    content = point.payload.get("page_content", "")
                    if not content and "content" in point.payload:
                        content = point.payload["content"]

                    results.append(
                        {
                            "id": point.id,
                            "content": content,
                            "metadata": point.payload.get("metadata", {}),
                            "score": 1.0,
                        }
                    )
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve by IDs: {e}")
            return []
