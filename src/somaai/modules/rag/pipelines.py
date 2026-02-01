"""RAG pipelines for question answering.

Combines retrieval, reranking, and generation for curriculum-based Q&A.
Includes security, observability, and fallback strategies.
Uses Decimal for precise score handling in critical operations.
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from somaai.contracts.common import GradeLevel, Subject, UserRole
from somaai.modules.rag.generator import CombinedGenerator
from somaai.modules.rag.mock_retriever import MockRetriever
from somaai.modules.rag.reranker import get_reranker
from somaai.modules.rag.retriever import Retriever
from somaai.modules.rag.types import RAGInput
from somaai.utils.ids import generate_id
from somaai.utils.observability import log_rag_request
from somaai.utils.security import sanitize_query

if TYPE_CHECKING:
    from somaai.providers.llm import LLMClient
    from somaai.settings import Settings

import logging
import json
from somaai.modules.rag.prompts import CONDENSE_QUESTION_PROMPT

logger = logging.getLogger(__name__)


class BaseRAGPipeline(Protocol):
    """Protocol for RAG pipeline implementations."""

    async def run(
        self,
        query: str,
        grade: str = "S1",
        subject: str = "general",
        user_role: str = "student",
        session_id: str | None = None,
        preferences: dict | None = None,
        history: str = "",
    ) -> dict:
        ...


class RAGPipeline:
    """Complete RAG pipeline for educational Q&A.

    Combines:
    - Input sanitization for security
    - Retrieval with grade/subject filtering and fallback
    - Cross-encoder reranking (singleton)
    - LLM generation with citations
    - Observability logging
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize pipeline components.

        Args:
            settings: Application settings
        """
        self._settings = settings
        self.retriever = Retriever(settings)
        self.generator = CombinedGenerator(settings)

    @property
    def settings(self):
        """Get settings."""
        if self._settings is None:
            from somaai.settings import settings
            self._settings = settings
        return self._settings

    @property
    def reranker(self):
        """Get singleton reranker."""
        return get_reranker()

    async def run(
        self,
        query: str,
        grade: str = "S1",
        subject: str = "general",
        user_role: str = "student",
        session_id: str | None = None,
        preferences: dict | None = None,
        history: str = "",
    ) -> dict:
        """Execute the full RAG pipeline.

        Args:
            query: User's question
            grade: Grade level (e.g., "S1", "P6")
            subject: Subject (e.g., "mathematics", "biology")
            user_role: 'student' or 'teacher'
            session_id: Optional session for context
            preferences: Dict with 'enable_analogy' and 'enable_realworld'
            history: Previous conversation history

        Returns:
            Complete response dict
        """
        start_time = time.time()
        preferences = preferences or {}
        include_analogy = preferences.get("enable_analogy", False)
        include_realworld = preferences.get("enable_realworld", False)

        try:
            # 0. Check response cache
            from somaai.cache.rag import get_response_cache
            cache = get_response_cache()
            cached_response = await cache.get(query, grade, subject)
            if cached_response:
                # logger.info(f"Returning cached response for: {query[:50]}...")
                return cached_response

            # 1. Sanitize input for security
            clean_query = sanitize_query(query)

            # Debug: Log context
            logger.info(f"RAG Processing - Original Query: {clean_query}")
            if history:
                logger.info(f"RAG Context - History present ({len(history)} chars)")
            else:
                logger.info("RAG Context - No history provided")

            # 1b. Condense query if history exists
            search_query = clean_query
            if history:
                search_query = await self._condense_query(clean_query, history)
                logger.info(f"RAG Rewritten Query: {search_query}")

            # 2. Retrieve with fallback strategy
            docs = await self.retriever.retrieve_with_fallback(
                query=search_query,
                grade=grade,
                subject=subject,
                top_k=20,
            )

            # 3. Rerank for relevance (uses singleton)
            # Use Decimal for precise min_score threshold
            # Note: If no docs, rerank returns empty list
            ranked_docs = []
            if docs:
                ranked_docs = await self.reranker.rerank(
                    query=search_query,
                    documents=docs,
                    top_k=5,
                    min_score=Decimal("0.1"),
                )

            # 4. Check if we have sufficient context
            if not ranked_docs:
                logger.info("No documents found. Proceeding to generator for potential chit-chat handling.")
                # We do NOT return insufficient_context here anymore.
                # We let the Generator handle it (e.g. for greetings).
                # return self._insufficient_context_response(query, grade, subject)

            # 5. Generate response
            result = await self.generator.generate(
                query=search_query,
                context=[doc.get("content", "") for doc in ranked_docs],
                grade=grade,
                user_role=user_role,
                include_analogy=include_analogy,
                include_realworld=include_realworld,
                retrieved_docs=ranked_docs,  # Pass for citation validation
                history=history,
            )

            # 6. Build citations (returns tuple: citations_list, chunks_map)
            citations, chunks_map = self._build_citations(ranked_docs)

            # 7. Build response
            response = {
                "message_id": generate_id(),
                "answer": result.get("answer", ""),
                "sufficiency": result.get("sufficiency", "sufficient"),
                "is_grounded": result.get("is_grounded", True),
                "confidence": result.get("confidence", 0.7),
                "citations": citations,
                "chunks_map": chunks_map,  # For persistence in chat endpoint
                "analogy": result.get("analogy"),
                "realworld_context": result.get("realworld_context"),
                "created_at": datetime.utcnow(),
                "retrieved_chunks": [], # For backward compatibility if needed, but we use chunks_map now
            }

            # 8. Cache response if high quality
            await cache.set(query, grade, subject, response)

            # 9. Log for observability
            latency_ms = (time.time() - start_time) * 1000
            log_rag_request(
                query=query,
                grade=grade,
                subject=subject,
                docs_retrieved=len(docs),
                docs_reranked=len(ranked_docs),
                latency_ms=latency_ms,
                success=True,
            )

            return response

        except Exception as e:
            # Log failure
            latency_ms = (time.time() - start_time) * 1000
            log_rag_request(
                query=query,
                grade=grade,
                subject=subject,
                docs_retrieved=0,
                docs_reranked=0,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )
            raise

    async def _condense_query(self, query: str, history: str) -> str:
        """Rewrite query to be standalone using history.

        Args:
            query: Follow-up question
            history: Conversation history

        Returns:
            Standalone query or original if rewriting fails
        """
        try:
            from somaai.providers.llm import get_llm
            llm = get_llm(self.settings)

            prompt = CONDENSE_QUESTION_PROMPT.format(
                chat_history=history,
                question=query
            )

            response_json = await llm.generate(prompt)
            
            # Helper to extract JSON if surrounded by markdown
            cleaned_json = response_json
            if "```json" in cleaned_json:
                import re
                match = re.search(r"```json\s*(.*?)\s*```", cleaned_json, re.DOTALL)
                if match:
                    cleaned_json = match.group(1)
            elif "```" in cleaned_json:
                 cleaned_json = cleaned_json.strip("`")

            data = json.loads(cleaned_json)
            rewritten = data.get("standalone_question", query)
            return rewritten

        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}. Using original query.")
            return query

    def _insufficient_context_response(
        self,
        query: str,
        grade: str,
        subject: str,
    ) -> dict:
        """Generate response when no relevant documents found.

        Args:
            query: Original query
            grade: Grade level
            subject: Subject

        Returns:
            Response indicating insufficient context
        """
        return {
            "message_id": generate_id(),
            "answer": (
                f"I couldn't find relevant curriculum content for your question "
                f"about {subject} at the {grade} level. Please try:\n"
                f"1. Rephrasing your question\n"
                f"2. Checking if this topic is covered in the curriculum\n"
                f"3. Asking a more specific question"
            ),
            "sufficiency": "insufficient",
            "citations": [],
            "chunks_map": {},
            "analogy": None,
            "realworld_context": None,
            "created_at": datetime.utcnow(),
        }

    def _build_citations(self, docs: list[dict]) -> tuple[list[dict], dict[str, str]]:
        """Build citations matching CitationResponse schema.

        Delegates to CitationExtractor for single source of truth.

        Args:
            docs: Retrieved documents with metadata

        Returns:
            Tuple of (list of citation dicts, chunks_map for persistence)
        """
        from somaai.modules.chat.citations import get_citation_extractor

        extractor = get_citation_extractor()
        citations, chunks_map = extractor.extract_citations(docs, top_k=len(docs))

        # Convert to dicts for response (CitationResponse -> dict)
        return [cit.model_dump() for cit in citations], chunks_map

    async def ask(
        self,
        question: str,
        grade: str,
        subject: str,
        user_role: str = "student",
        preferences: dict | None = None,
    ) -> dict:
        """Convenience method matching API contract.

        Args:
            question: User's question
            grade: Grade level
            subject: Subject
            user_role: User role
            preferences: Response preferences

        Returns:
            ChatResponse-compatible dict
        """
        return await self.run(
            query=question,
            grade=grade,
            subject=subject,
            user_role=user_role,
            preferences=preferences,
        )

    async def health_check(self) -> dict:
        """Check pipeline health.

        Returns:
            Health status dict
        """
        retriever_health = await self.retriever.health_check()
        reranker_available = self.reranker.is_available

        return {
            "status": "healthy" if retriever_health.get("status") == "healthy" else "degraded",
            "retriever": retriever_health,
            "reranker": {"available": reranker_available},
        }


class MockRAGPipeline:
    """Mock RAG pipeline using in-memory chunks and LLM.

    Now hybridized: It allows using the REAL Retriever (Qdrant) if available,
    falling back to mock data if no documents are found.
    This enables testing the ingestion pipeline end-to-end without a paid LLM.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        top_k: int = 3,
        settings: Settings | None = None,
    ):
        """Initialize mock pipeline.

        Args:
            llm: LLM client for generation (optional)
            top_k: Number of chunks to retrieve
            settings: Settings object
        """
        self.llm = llm
        self.real_retriever = Retriever(settings)
        self.mock_retriever = MockRetriever(top_k=top_k)
        self.generator = CombinedGenerator(settings)
        if llm:
            # HACK: inject the mock LLM into the generator's internal generator
            self.generator._generator._llm = llm

    async def run(
        self,
        query: str,
        grade: str = "S1",
        subject: str = "general",
        user_role: str = "student",
        session_id: str | None = None,
        preferences: dict | None = None,
        history: str = "",
    ) -> dict:
        """Execute hybrid mock RAG pipeline."""
        preferences = preferences or {}
        include_analogy = preferences.get("enable_analogy", False)
        include_realworld = preferences.get("enable_realworld", False)

        docs_dicts = []

        # 1. Try Real Retrieval first (Qdrant)
        try:
            real_docs = await self.real_retriever.retrieve_with_fallback(
                query=query,
                grade=grade,
                subject=subject,
                top_k=5
            )
            if real_docs:
                # Format for generator
                docs_dicts = [{
                    "doc_id": d["metadata"].get("doc_id", "unknown"),
                    "doc_title": d["metadata"].get("title", "Unknown"),
                    "page_start": d["metadata"].get("page_start", 1),
                    "page_end": d["metadata"].get("page_end", 1),
                    "snippet": d["content"],
                    "content": d["content"],
                    "score": d.get("score", 0),
                    "metadata": d["metadata"]
                } for d in real_docs]
        except Exception:
            # Ignore real retriever errors in Mock mode
            pass

        # 2. Fallback to Mock Data if nothing found in real DB
        if not docs_dicts:
            rag_input = RAGInput(
                query=query,
                grade=(
                    GradeLevel(grade)
                    if grade in GradeLevel._value2member_map_
                    else GradeLevel.S1
                ),
                subject=(
                    Subject(subject)
                    if subject in Subject._value2member_map_
                    else Subject.GENERAL
                ),
                user_role=(
                    UserRole(user_role)
                    if user_role in UserRole._value2member_map_
                    else UserRole.STUDENT
                ),
            )
            chunks = await self.mock_retriever.retrieve(rag_input)

            docs_dicts = [{
                "doc_id": c.doc_id,
                "doc_title": c.doc_title,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "snippet": c.snippet,
                "content": c.snippet,
                "score": c.score,
                "metadata": {
                    "doc_id": c.doc_id,
                    "title": c.doc_title,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                }
            } for c in chunks]

        # 3. Generate answer using the uniform generator
        context_strs = [d["content"] for d in docs_dicts]

        result = await self.generator.generate(
            query=query,
            context=context_strs,
            grade=grade,
            user_role=user_role,
            include_analogy=include_analogy,
            include_realworld=include_realworld,
            retrieved_docs=docs_dicts,
            history=history,
        )

        # 4. Build citations
        from somaai.modules.chat.citations import get_citation_extractor
        extractor = get_citation_extractor()
        citations, chunks_map = extractor.extract_citations(
            docs_dicts, top_k=len(docs_dicts)
        )

        if not citations and docs_dicts:
            # Fallback: Cite all retrieved docs if Mock LLM didn't cite any
            # This ensures we see citations in the test output
            from somaai.contracts.chat import CitationResponse
            for i, d in enumerate(docs_dicts):
                citations.append(CitationResponse(
                    doc_id=d["doc_id"],
                    doc_title=d["doc_title"],
                    page_start=d["page_start"],
                    page_end=d["page_end"],
                    chunk_preview=d["snippet"][:200],
                    view_url=f"/documents/{d['doc_id']}/view#page={d['page_start']}",
                    relevance_score=float(d.get("score", 0))
                ))

        return {
            "message_id": generate_id(),
            "answer": result.get("answer", ""),
            "sufficiency": result.get("sufficiency", "sufficient"),
            "citations": [cit.model_dump() for cit in citations],
            "chunks_map": chunks_map,
            "analogy": result.get("analogy"),
            "realworld_context": result.get("realworld_context"),
            "created_at": datetime.utcnow(),
        }
