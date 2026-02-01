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
    ) -> tuple[list[CitationResponse], dict[str, str]]:
        """Extract citations from retrieved chunks.

        This is the single source of truth for citation building.
        RAGPipeline should use this instead of its own _build_citations.

        Args:
            chunks: List of chunk dictionaries from RAG pipeline

        Returns:
            Tuple of:
                - List of CitationResponse objects
                - chunks_map: Dict mapping "doc_id:page" -> chunk_id for persistence
        """
        citations = []
        chunks_map = {}  # For linking back to chunk_id during save
        seen = set()

        # Sort by score descending
        sorted_chunks = sorted(
            chunks,
            key=lambda x: float(x.get("rerank_score", x.get("score", 0))),
            reverse=True
        )

        for doc in sorted_chunks:
            if len(citations) >= top_k:
                break

            meta = doc.get("metadata", {})
            doc_id = meta.get("doc_id", "unknown")
            page = meta.get("page_start", 1)
            chunk_id = meta.get("chunk_id")

            # Deduplicate by doc_id + page
            key = f"{doc_id}:{page}"
            if key in seen:
                continue
            seen.add(key)

            # Track chunk_id for persistence
            if chunk_id:
                chunks_map[key] = chunk_id

            score = float(doc.get("rerank_score", doc.get("score", 0)))

            citations.append(CitationResponse(
                doc_id=doc_id,
                doc_title=meta.get("title", "Unknown Document"),
                page_start=page,
                page_end=meta.get("page_end", page),
                chunk_preview=doc.get("content", "")[:200],
                view_url=self._format_view_url(doc_id, page),
                relevance_score=round(min(score, 1.0), 3),  # Clamp to 0-1
            ))

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
            citations.append(CitationResponse(
                doc_id=chunk.document_id,
                doc_title=doc.title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_preview=citation.snippet or chunk.content[:200],
                view_url=self._format_view_url(chunk.document_id, chunk.page_start),
                relevance_score=citation.relevance_score or 0.0,
            ))

        return citations

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
            chunks_map: Mapping from extract_citations ("doc_id:page" -> chunk_id)
        """
        for i, cit in enumerate(citations):
            key = f"{cit.doc_id}:{cit.page_start}"
            chunk_id = chunks_map.get(key)

            if not chunk_id:
                # Skip citations we can't link to a chunk
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
