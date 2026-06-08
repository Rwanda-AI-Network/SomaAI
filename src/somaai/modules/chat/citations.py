"""Chat citation extraction and management.

Provides utilities for extracting citations from RAG results,
persisting them with messages, and retrieving them later.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.chat import CitationResponse
from somaai.db.models import Chunk, Document, MessageCitation
from somaai.utils.ids import generate_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CitationExtractor:
    """Manages citations for chat messages.

    Links AI responses to source documents for transparency
    and verification.

    Usage:
        extractor = CitationExtractor()

        # Extract from RAG chunks (returns CitationResponse + chunk_id for persistence)
        citations, chunks_map = extractor.extract_citations(ranked_docs)

        # Save to DB
        await extractor.save_citations(db, message_id, citations, chunks_map)

        # Later, retrieve
        citations = await extractor.get_message_citations(db, message_id)
    """

    def extract_citations(
        self,
        chunks: list[dict],
        top_k: int = 5,
        min_score: float = 0.4,
    ) -> tuple[list[CitationResponse], dict[str, str]]:
        """Extract citations from retrieved chunks.

        This is the single source of truth for citation building.
        RAGPipeline should use this instead of its own _build_citations.

        Args:
            chunks: List of chunk dictionaries from RAG pipeline
            top_k: Maximum number of citations to return
            min_score: Minimum relevance score to include

        Returns:
            Tuple of:
                - List of CitationResponse objects
                - chunks_map: Dict mapping chunk_id -> CitationResponse index
                  for persistence. Keys are chunk_ids (not composite doc+page)
                  to avoid collisions when multiple chunks share the same page.
        """
        citations = []
        # chunk_id -> order index; used by save_citations for FK resolution.
        # Keyed by chunk_id directly to avoid doc+page collision.
        chunks_map: dict[str, str] = {}
        seen: set[str] = set()

        # Sort by score descending
        sorted_chunks = sorted(
            chunks,
            key=lambda x: float(x.get("rerank_score", x.get("score", 0))),
            reverse=True,
        )

        for doc in sorted_chunks:
            if len(citations) >= top_k:
                break

            meta = doc.get("metadata", {})
            doc_id = meta.get("doc_id", "unknown")
            page = meta.get("page_start", 1)
            chunk_id = meta.get("chunk_id")

            score = float(doc.get("rerank_score", doc.get("score", 0)))

            # Skip low-relevance chunks
            if score < min_score:
                continue

            # Deduplicate by doc_id + page (same document page = same content)
            dedup_key = f"{doc_id}:{page}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Track chunk_id for persistence — keyed by chunk_id directly
            # so each citation maps unambiguously to its source chunk.
            if chunk_id:
                chunks_map[chunk_id] = chunk_id

            citations.append(
                CitationResponse(
                    doc_id=doc_id,
                    doc_title=meta.get("title", "Unknown Document"),
                    section_title=meta.get("section_title"),
                    page_start=page,
                    page_end=meta.get("page_end", page),
                    chunk_preview=doc.get("content", "")[:200],
                    view_url=self._format_view_url(doc_id, page),
                    relevance_score=round(min(score, 1.0), 3),  # Clamp to 0-1
                )
            )

        return citations, chunks_map

    async def get_message_citations(
        self,
        db: AsyncSession,
        message_id: str,
    ) -> list[CitationResponse]:
        """Get citations for a previously saved message.

        Performs a 3-way join: MessageCitation -> Chunk -> Document
        to return complete citation data with document titles.

        Args:
            db: Database session
            message_id: Message identifier

        Returns:
            Citations associated with the message, ordered by relevance
        """
        stmt = (
            select(MessageCitation, Chunk, Document)
            .join(Chunk, MessageCitation.chunk_id == Chunk.id)
            .join(Document, Chunk.document_id == Document.id)
            .where(MessageCitation.message_id == message_id)
            .order_by(MessageCitation.order)
        )
        result = await db.execute(stmt)
        rows = result.all()

        citations = []
        for citation, chunk, doc in rows:
            # section_title is stored in chunk metadata_json (Qdrant mirror)
            chunk_meta = chunk.metadata_json if hasattr(chunk, "metadata_json") else {}
            section_title = (
                chunk_meta.get("section_title")
                if isinstance(chunk_meta, dict)
                else None
            )
            citations.append(
                CitationResponse(
                    doc_id=chunk.document_id,
                    doc_title=doc.title,
                    section_title=section_title,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_preview=citation.snippet or chunk.content[:200],
                    view_url=self._format_view_url(chunk.document_id, chunk.page_start),
                    relevance_score=citation.relevance_score or 0.0,
                )
            )

        return citations

    async def get_citations_batch(
        self,
        db: AsyncSession,
        message_ids: list[str],
    ) -> dict[str, list[CitationResponse]]:
        """Get citations for multiple messages in a single query (batch loading).

        This is a performance optimization to avoid N+1 queries when loading
        citations for multiple messages (e.g., in list_messages).

        Args:
            db: Database session
            message_ids: List of message identifiers

        Returns:
            Dictionary mapping message_id -> list of CitationResponse
        """
        if not message_ids:
            return {}

        # Single query to load all citations for all messages
        stmt = (
            select(MessageCitation, Chunk, Document)
            .join(Chunk, MessageCitation.chunk_id == Chunk.id)
            .join(Document, Chunk.document_id == Document.id)
            .where(MessageCitation.message_id.in_(message_ids))
            .order_by(MessageCitation.message_id, MessageCitation.order)
        )
        result = await db.execute(stmt)
        rows = result.all()

        # Group citations by message_id
        citations_by_message: dict[str, list[CitationResponse]] = {
            msg_id: [] for msg_id in message_ids
        }

        for citation, chunk, doc in rows:
            # section_title is stored in chunk metadata_json (Qdrant mirror)
            chunk_meta = chunk.metadata_json if hasattr(chunk, "metadata_json") else {}
            section_title = (
                chunk_meta.get("section_title")
                if isinstance(chunk_meta, dict)
                else None
            )

            citation_response = CitationResponse(
                doc_id=chunk.document_id,
                doc_title=doc.title,
                section_title=section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_preview=citation.snippet or chunk.content[:200],
                view_url=self._format_view_url(chunk.document_id, chunk.page_start),
                relevance_score=citation.relevance_score or 0.0,
            )

            citations_by_message[citation.message_id].append(citation_response)

        return citations_by_message

    async def save_citations(
        self,
        db: AsyncSession,
        message_id: str,
        citations: list[CitationResponse],
        chunks_map: dict[str, str],
    ) -> None:
        """Save citations to database linking message to chunks.

        Note: This method adds to the session but does NOT commit.
        The caller is responsible for committing the transaction.

        Args:
            db: Database session
            message_id: Message identifier
            citations: CitationResponse objects from extract_citations
            chunks_map: Mapping from extract_citations (chunk_id -> chunk_id)
        """
        import logging

        logger = logging.getLogger(__name__)

        # chunks_map preserves insertion order (Python 3.7+) and was built
        # in the same pass as citations, so index i in citations maps to
        # index i in chunks_map.values(). This is O(1) per citation.
        chunk_ids = list(chunks_map.values())

        if not chunk_ids:
            return

        # Batch-verify which chunk_ids actually exist in PostgreSQL.
        # This prevents FK violations when Qdrant has stale data.
        result = await db.execute(select(Chunk.id).where(Chunk.id.in_(chunk_ids)))
        valid_chunk_ids = {row[0] for row in result}

        skipped = 0
        saved = 0

        for i, cit in enumerate(citations):
            chunk_id = chunk_ids[i] if i < len(chunk_ids) else None

            if not chunk_id:
                continue

            if chunk_id not in valid_chunk_ids:
                skipped += 1
                continue

            db_citation = MessageCitation(
                id=generate_id(),
                message_id=message_id,
                chunk_id=chunk_id,
                relevance_score=cit.relevance_score,
                order=i,
                snippet=cit.chunk_preview,
            )
            db.add(db_citation)
            saved += 1

        if skipped:
            logger.warning(
                "Skipped %d citation(s): chunk_ids not found in PostgreSQL "
                "(Qdrant/PostgreSQL may be out of sync)",
                skipped,
                extra={"message_id": message_id, "saved": saved, "skipped": skipped},
            )

    def _format_view_url(self, doc_id: str, page_number: int) -> str:
        """Generate stable view URL for a citation."""
        return f"/api/v1/docs/{doc_id}/view?page={page_number}"


# Singleton for convenience
_extractor: CitationExtractor | None = None


def get_citation_extractor() -> CitationExtractor:
    """Get singleton CitationExtractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = CitationExtractor()
    return _extractor
