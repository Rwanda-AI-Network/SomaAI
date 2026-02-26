"""RAG pipeline for curriculum Q&A.

Combines retrieval and generation for educational question answering.
Includes security, caching, debug logging, and fallback strategies.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Protocol

from somaai.modules.rag.generator import LLMGenerator
from somaai.modules.rag.prompts import CONDENSE_QUESTION_PROMPT
from somaai.modules.rag.query_classifier import classify_query
from somaai.modules.rag.retriever import Retriever
from somaai.utils.ids import generate_id
from somaai.utils.observability import log_rag_request
from somaai.utils.security import sanitize_query
from somaai.utils.time import utc_now

if TYPE_CHECKING:
    from somaai.settings import Settings

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
    ) -> dict: ...


class RAGPipeline:
    """RAG pipeline for educational Q&A.

    Pipeline stages:
    1. Input sanitization + query condensation (if history)
    2. Retrieval with grade filtering and fallback
    3. LLM generation with citations
    4. Response caching and observability logging
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize pipeline components.

        Args:
            settings: Application settings
        """
        self._settings = settings
        self.retriever = Retriever(settings)
        self.generator = LLMGenerator(settings)

    @property
    def settings(self):
        """Get settings."""
        if self._settings is None:
            from somaai.settings import settings

            self._settings = settings
        return self._settings

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
        """Execute the RAG pipeline.

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

        # Initialize debugger (no-op when disabled)
        from somaai.utils.debug import PipelineDebugger

        debug = PipelineDebugger(enabled=getattr(self.settings, "debug", False))
        debug.start(query, grade, subject)

        # Track metrics
        try:
            from somaai.monitoring import rag_latency_seconds

            monitor_latency = True
        except ImportError:
            monitor_latency = False

        try:
            # 0. Check response cache
            from somaai.cache.rag import get_response_cache

            cache = get_response_cache()
            cached_response = await cache.get(query, grade, subject)
            if cached_response:
                debug.log_stage("cache", hit=True)
                return cached_response

            # 1. Sanitize input
            clean_query = sanitize_query(query)
            debug.log_stage("sanitize", query=clean_query)

            # 1.5. Classify query — skip RAG for greetings/chitchat
            query_type, direct_response = classify_query(clean_query)
            if query_type == "chitchat":
                debug.log_stage("classify", type="chitchat")
                return {
                    "message_id": generate_id(),
                    "answer": direct_response,
                    "sufficiency": "sufficient",
                    "is_grounded": True,
                    "confidence": 1.0,
                    "citations": [],
                    "chunks_map": {},
                    "analogy": None,
                    "realworld_context": None,
                    "created_at": utc_now(),
                    "retrieved_chunks": [],
                }
            debug.log_stage("classify", type="curriculum")

            # 2. Query condensation (only if history exists)
            search_query = clean_query
            if history and history.strip():
                search_query = await self._condense_query(clean_query, history)
                debug.log_stage(
                    "condense",
                    original=clean_query,
                    condensed=search_query,
                )

            # 3. Retrieve relevant documents
            docs, context_str = await self.retriever.retrieve_for_context(
                query=search_query,
                grade=grade,
                subject=subject,
                use_fallback=True,
            )

            debug.log_stage(
                "retrieve",
                docs_found=len(docs),
                top_score=docs[0].get("score", 0) if docs else 0,
                context_length=len(context_str),
            )

            # 4. Check if we have sufficient context
            if not docs:
                logger.info("No documents found. Returning insufficient context.")
                response = self._insufficient_context_response(query, grade, subject)
                debug.end(response)
                return response

            # 5. Generate response
            result = await self.generator.generate(
                query=search_query,
                context=context_str,
                grade=grade,
                user_role=user_role,
                include_analogy=include_analogy,
                include_realworld=include_realworld,
                retrieved_docs=docs,
                history=history,
            )

            debug.log_stage(
                "generate",
                sufficiency=result.get("sufficiency"),
                confidence=result.get("confidence"),
                is_grounded=result.get("is_grounded"),
            )

            # 6. Build citations — cross-reference LLM's cited pages
            #    with retrieved docs so only actually-used sources appear
            llm_citations = result.get("citations_validated", [])
            citations, chunks_map = self._build_citations(
                docs, llm_citations=llm_citations
            )

            # 7. Build response
            response = {
                "message_id": generate_id(),
                "answer": result.get("answer", ""),
                "sufficiency": result.get("sufficiency", "sufficient"),
                "is_grounded": result.get("is_grounded", True),
                "confidence": result.get("confidence", 0.7),
                "citations": citations,
                "chunks_map": chunks_map,
                "analogy": result.get("analogy"),
                "realworld_context": result.get("realworld_context"),
                "created_at": utc_now(),
                "retrieved_chunks": [],
            }

            # 8. Cache response
            await cache.set(query, grade, subject, response)

            # 9. Log for observability
            latency_ms = (time.time() - start_time) * 1000

            if monitor_latency:
                rag_latency_seconds.labels(stage="total").observe(latency_ms / 1000)

            try:
                from somaai.monitoring import (
                    log_rag_request as log_rag_metrics,
                )

                log_rag_metrics(
                    query=query,
                    grade=grade,
                    subject=subject,
                    user_role=user_role,
                    docs_retrieved=len(docs),
                    docs_reranked=len(docs),
                    latency_ms=latency_ms,
                    success=True,
                    confidence=float(response.get("confidence", 0)),
                    sufficiency=response.get("sufficiency", "unknown"),
                )
            except ImportError:
                log_rag_request(
                    query=query,
                    grade=grade,
                    subject=subject,
                    docs_retrieved=len(docs),
                    docs_reranked=len(docs),
                    latency_ms=latency_ms,
                    success=True,
                )

            debug.end(response)
            return response

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            try:
                from somaai.monitoring import (
                    log_rag_request as log_rag_metrics,
                )

                log_rag_metrics(
                    query=query,
                    grade=grade,
                    subject=subject,
                    user_role=user_role,
                    docs_retrieved=0,
                    docs_reranked=0,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(e),
                )
            except ImportError:
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
        if not history or not history.strip():
            return query

        try:
            from somaai.providers.llm import get_llm

            llm = get_llm(self.settings)

            prompt = CONDENSE_QUESTION_PROMPT.format(
                chat_history=history, question=query
            )

            response_json = await llm.generate(prompt)

            # Extract JSON if surrounded by markdown
            import re

            cleaned_json = response_json
            if "```json" in cleaned_json:
                match = re.search(r"```json\s*(.*?)\s*```", cleaned_json, re.DOTALL)
                if match:
                    cleaned_json = match.group(1)
            elif "```" in cleaned_json:
                cleaned_json = cleaned_json.strip("`")

            data = json.loads(cleaned_json)
            rewritten = data.get("standalone_question", query)
            return rewritten

        except Exception as e:
            logger.warning("Query rewriting failed: %s. Using original query.", e)
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
            "created_at": utc_now(),
        }

    def _build_citations(
        self,
        docs: list[dict],
        llm_citations: list[dict] | None = None,
    ) -> tuple[list[dict], dict[str, str]]:
        """Build citations matching CitationResponse schema.

        Cross-references the LLM's cited page numbers with retrieved
        chunks so only actually-used sources appear. Falls back to
        the top-5 retrieved chunks by relevance score.

        Args:
            docs: Retrieved documents with metadata
            llm_citations: LLM's validated citations list, each with
                           'page_number' and optionally 'valid' flag

        Returns:
            Tuple of (list of citation dicts, chunks_map)
        """
        from somaai.modules.chat.citations import get_citation_extractor

        extractor = get_citation_extractor()

        # If the LLM provided citations, filter docs to only those
        # whose page numbers were actually cited in the answer.
        cited_docs = docs
        if llm_citations:
            cited_pages = {
                int(c["page_number"])
                for c in llm_citations
                if c.get("valid", True) and c.get("page_number")
            }
            if cited_pages:
                cited_docs = [
                    d
                    for d in docs
                    if d.get("metadata", {}).get("page_start") in cited_pages
                ]
                # If cross-referencing found matches, use them.
                # Otherwise fall back to full doc list (model may
                # have cited pages that don't match metadata exactly).
                if not cited_docs:
                    cited_docs = docs

        citations, chunks_map = extractor.extract_citations(cited_docs, top_k=5)

        return [cit.model_dump() for cit in citations], chunks_map

    async def health_check(self) -> dict:
        """Check pipeline health.

        Returns:
            Health status dict
        """
        retriever_health = await self.retriever.health_check()

        return {
            "status": (
                "healthy" if retriever_health.get("status") == "healthy" else "degraded"
            ),
            "retriever": retriever_health,
        }
