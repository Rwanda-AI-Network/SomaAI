"""RAG generator for response synthesis.

Generates curriculum-aligned responses using LLM with retrieved context.
Supports structured JSON output and citation validation.
Uses Decimal for precise confidence score handling.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from somaai.modules.rag.prompts import (
    SYSTEM_PROMPT,
    HYDE_PROMPT,
    format_prompt,
    get_prompt_for_role,
)
from somaai.modules.rag.schemas import (
    parse_grounded_response,
    validate_citations,
)

if TYPE_CHECKING:
    from somaai.settings import Settings

logger = logging.getLogger(__name__)


from decimal import Decimal

def calibrate_confidence(
    llm_confidence: float,
    retrieval_scores: list[float],
    num_docs_retrieved: int,
    min_docs_expected: int = 3
) -> float:
    """Calibrate LLM confidence based on retrieval quality.
    
    Adjusts raw LLM confidence by considering:
    1. Average retrieval score (40% weight)
    2. Document coverage (20% weight)
    3. LLM confidence (40% weight)
    
    Args:
        llm_confidence: Raw confidence from LLM (0-1)
        retrieval_scores: Relevance scores of retrieved docs
        num_docs_retrieved: Number of docs retrieved
        min_docs_expected: Minimum expected docs for good coverage
        
    Returns:
        Calibrated confidence (0-1)
        
    Example:
        >>> calibrate_confidence(0.9, [0.8, 0.7, 0.6], 3, 3)
        0.83  # Slightly lower due to retrieval quality
    """
    # Input validation (Bug #3 fix: prevent division by zero)
    if not retrieval_scores:
        return 0.0
    
    if min_docs_expected <= 0:
        logger.warning(f"Invalid min_docs_expected={min_docs_expected}, using 3")
        min_docs_expected = 3
    
    # Convert to Decimal for precision (Bug #3 fix: consistent types)
    llm_conf = Decimal(str(llm_confidence))
    scores_decimal = [Decimal(str(s)) for s in retrieval_scores]
    
    # Factor 1: Average retrieval quality (40% weight)
    avg_retrieval_score = sum(scores_decimal) / len(scores_decimal)
    retrieval_factor = avg_retrieval_score * Decimal("0.4")
    
    # Factor 2: Document coverage (20% weight)
    coverage_ratio = min(
        Decimal(str(num_docs_retrieved)) / Decimal(str(min_docs_expected)),
        Decimal("1.0")
    )
    coverage_factor = coverage_ratio * Decimal("0.2")
    
    # Factor 3: LLM confidence (40% weight)
    llm_factor = llm_conf * Decimal("0.4")
    
    # Combine factors
    calibrated = retrieval_factor + coverage_factor + llm_factor
    
    # FIXED (Bug #3): Apply graduated penalty based on top retrieval score
    # Old logic was too harsh with flat 30% penalty
    # New logic: graduated penalty from 50% (worst) to 70% (threshold)
    max_score = max(scores_decimal)
    if max_score < Decimal("0.5"):
        # Graduated penalty: worse top match = stronger penalty
        # Range: 0.5 (max_score=0) to 0.7 (max_score=0.5)
        penalty_factor = Decimal("0.5") + (max_score * Decimal("0.4"))
        calibrated *= penalty_factor
        logger.debug(
            f"Applied penalty: max_score={float(max_score):.2f}, "
            f"penalty_factor={float(penalty_factor):.2f}"
        )
    
    # Ensure bounds [0, 1]
    calibrated = max(Decimal("0.0"), min(calibrated, Decimal("1.0")))
    
    return float(calibrated)


class BaseGenerator:
    """Abstract base class for RAG context-based generators."""

    async def generate(self, query: str, context: list[str]) -> str:
        """Generate a response based on the query and provided context."""
        raise NotImplementedError


class LLMGenerator(BaseGenerator):
    """LLM-based response generator with structured output.

    Uses configured LLM provider to generate responses
    with curriculum context and validates citations.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize generator."""
        self._settings = settings
        self._llm = None

    @property
    def settings(self):
        """Get settings."""
        if self._settings is None:
            from somaai.settings import settings

            self._settings = settings
        return self._settings

    @property
    def llm(self):
        """Get LLM client."""
        if self._llm is None:
            from somaai.providers.llm import get_llm

            self._llm = get_llm(self.settings)
        return self._llm

    async def generate(
        self,
        query: str,
        context: str,
        grade: str = "S1",
        user_role: str = "student",
        include_analogy: bool = False,
        include_realworld: bool = False,
        retrieved_docs: list[dict] | None = None,
        history: str = "",
    ) -> dict:
        """Generate response with structured output.

        Args:
            query: User's question
            context: Formatted context from retrieval
            grade: Grade level
            user_role: 'student' or 'teacher'
            include_analogy: Include analogy
            include_realworld: Include real-world examples
            retrieved_docs: Original docs for citation validation
            history: Previous chat history

        Returns:
            Dict with answer, sufficiency, citations, validation status
        """
        # Get appropriate prompt template
        template = get_prompt_for_role(user_role)

        # Format prompt
        prompt = format_prompt(
            template=template,
            question=query,
            context=context,
            grade=grade,
            include_analogy=include_analogy,
            include_realworld=include_realworld,
            history=history,
        )

        # Add system prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

        # Generate response
        try:
            response = await self.llm.generate(full_prompt)
        except Exception as e:
            logger.error(f"LLM generation failed: {str(e)}")
            return {
                "answer": (
                    "I encountered an error while processing your request. "
                    "Please try refining your question."
                ),
                "sufficiency": "insufficient",
                "is_grounded": False,
                "confidence": 0.0,
                "citations_validated": [],
                "citations_all_valid": False,
                "reasoning": "",
                "analogy": None,
                "realworld_context": None,
            }

        # Try to parse structured output
        parsed = parse_grounded_response(response)

        if parsed:
            # Validate citations against retrieved docs
            if retrieved_docs:
                citations_valid, validated_citations = validate_citations(
                    parsed, retrieved_docs
                )
            else:
                citations_valid = True
                validated_citations = [
                    {"page_number": c.page_number, "quote": c.quote, "valid": True}
                    for c in parsed.citations
                ]

            # Determine sufficiency from structured response
            # Use Decimal for precise confidence comparisons
            confidence = Decimal(str(parsed.confidence))
            if not parsed.is_grounded or confidence < Decimal("0.3"):
                sufficiency = "insufficient"
            elif confidence < Decimal("0.7"):
                sufficiency = "partial"
            else:
                sufficiency = "sufficient"

            logger.info(
                f"Structured response: grounded={parsed.is_grounded}, "
                f"confidence={confidence}, citations_valid={citations_valid}"
            )

            return {
                "answer": parsed.answer,
                "sufficiency": sufficiency,
                "is_grounded": parsed.is_grounded,
                "confidence": parsed.confidence,
                "citations_validated": validated_citations,
                "citations_all_valid": citations_valid,
                "reasoning": parsed.reasoning,
                "analogy": parsed.analogy,
                "realworld_context": parsed.realworld_context,
            }

        # Fallback: unstructured response
        logger.warning("Failed to parse structured output, using fallback")
        return self._parse_unstructured(response, include_analogy, include_realworld)

    def _parse_unstructured(
        self,
        response: str,
        include_analogy: bool,
        include_realworld: bool,
    ) -> dict:
        """Parse unstructured response (fallback).

        Args:
            response: Raw LLM response
            include_analogy: Extract analogy section
            include_realworld: Extract real-world section

        Returns:
            Response dict
        """
        sufficiency = "sufficient"
        lower = response.lower()

        if "don't have" in lower or "not in the curriculum" in lower:
            sufficiency = "insufficient"
        elif "partial" in lower or "limited information" in lower:
            sufficiency = "partial"

        return {
            "answer": response,
            "sufficiency": sufficiency,
            "is_grounded": True,  # Assume grounded in fallback
            "confidence": 0.7,
            "citations_validated": [],
            "citations_all_valid": False,
            "reasoning": "",
            "analogy": (
                self._extract_section(response, "Analogy") if include_analogy else None
            ),
            "realworld_context": (
                self._extract_section(response, "Real-World")
                if include_realworld
                else None
            ),
        }

    async def generate_hypothetical_answer(self, query: str) -> str:
        """Generate a hypothetical answer for HyDE.
        
        Args:
            query: User question
            
        Returns:
            Hypothetical answer string
        """
        # Simple HyDE prompt
        prompt = HYDE_PROMPT.format(question=query)
        
        try:
            response = await self.llm.generate(prompt)
            return response.strip()
        except Exception as e:
            logger.warning(f"HyDE generation failed: {e}")
            return query  # Fallback to original query

    def _extract_section(self, text: str, section_name: str) -> str | None:
        """Extract a section from the response."""
        import re

        pattern = rf"\*\*{section_name}.*?\*\*:?\s*(.*?)(?=\n\n\*\*|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None


class CombinedGenerator(BaseGenerator):
    """Synthesizes multiple generation strategies into a unified response."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._generator = LLMGenerator(settings)

    async def generate(
        self,
        query: str,
        context: list[str],
        grade: str = "S1",
        user_role: str = "student",
        include_analogy: bool = False,
        include_realworld: bool = False,
        retrieved_docs: list[dict] | None = None,
        history: str = "",
    ) -> dict:
        """Generate combined response.

        Args:
            query: User question
            context: List of context strings
            grade: Grade level
            user_role: 'student' or 'teacher'
            include_analogy: Include analogy
            include_realworld: Include real-world
            retrieved_docs: Original docs for citation validation
            history: Previous chat history

        Returns:
            Complete response dict
        """
        context_str = "\n---\n".join(context)
        return await self._generator.generate(
            query=query,
            context=context_str,
            grade=grade,
            user_role=user_role,
            include_analogy=include_analogy,
            include_realworld=include_realworld,
            retrieved_docs=retrieved_docs,
            history=history,
        )
