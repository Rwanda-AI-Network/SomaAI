"""RAG generator for response synthesis.

Generates curriculum-aligned responses using LLM with retrieved context.
Supports structured JSON output and citation validation.
Includes follow-up detection to inject anti-repetition instructions.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from somaai.modules.rag.prompts import (
    SYSTEM_PROMPT,
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


# ── Follow-up detection (regex, zero latency) ───────────────────────────
_FOLLOW_UP_RE = re.compile(
    r"(explain\s*(more|further|again|that|it)"
    r"|what\s*do\s*you\s*mean|can\s*you\s*(clarify|elaborate)"
    r"|i\s*don'?t\s*(understand|get)"
    r"|tell\s*me\s*more|go\s*deeper|in\s*depth"
    r"|more\s*(detail|example|info)"
    r"|give\s*me\s*(a|an|more)\s*(example|code)"
    r"|why\s*is\s*that|how\s*(so|come)|what\s*about)",
    re.IGNORECASE,
)


def _is_follow_up(query: str, has_history: bool) -> bool:
    """Check if query is a follow-up to a previous answer."""
    if not has_history:
        return False
    return bool(_FOLLOW_UP_RE.search(query.strip()))


def _is_repeat_question(query: str, history: str) -> bool:
    """Check if user is asking the same question again.

    Compares against previous user messages in the history string.
    """
    if not history:
        return False
    normalized = query.lower().strip().rstrip("?!.")
    # History format is "User: ...", "SomaAI: ..." lines
    for line in history.split("\n"):
        if line.lower().startswith("user:"):
            prev = line.split(":", 1)[1].strip().lower().rstrip("?!.")
            if prev == normalized:
                return True
    return False


def _get_previous_answer(history: str) -> str:
    """Extract the last assistant answer from history string.

    History format is multi-line:
        User: question
        Assistant: line 1 of answer
        line 2 of answer
        ...
        User: next question

    We walk backwards to find the last "Assistant:" / "SomaAI:" block
    and collect every line until we hit the previous "User:" line.
    """
    if not history:
        return ""
    lines = history.split("\n")
    answer_lines: list[str] = []
    collecting = False

    # Walk backwards through lines
    for line in reversed(lines):
        lower = line.lower().strip()
        if collecting:
            # Stop when we hit the "Assistant:" header itself
            if lower.startswith("somaai:") or lower.startswith("assistant:"):
                answer_lines.append(line.split(":", 1)[1].strip())
                break
            # Stop if we hit a previous user turn
            if lower.startswith("user:"):
                break
            answer_lines.append(line)
        else:
            # Start collecting when we first encounter a non-User line
            # that comes before the latest "User:" line (i.e. the answer block)
            if lower.startswith("user:"):
                collecting = True
                continue

    answer_lines.reverse()
    result = "\n".join(answer_lines).strip()
    if result:
        logger.debug(
            "Extracted previous answer (%d chars): %s...",
            len(result),
            result[:120],
        )
    return result


class LLMGenerator:
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
        subject: str = "general",
        user_role: str = "student",
        include_analogy: bool = False,
        include_realworld: bool = False,
        retrieved_docs: list[dict] | None = None,
        history: str = "",
    ) -> dict:
        """Generate response with structured output.

        Args:
            query: User's question
            context: Formatted context string from retrieval
            grade: Grade level
            user_role: 'student' or 'teacher'
            include_analogy: Include analogy
            include_realworld: Include real-world examples
            retrieved_docs: Original docs for citation validation
            history: Previous chat history

        Returns:
            Dict with answer, sufficiency, citations, validation status
        """
        # Detect follow-up or repeat question and get previous answer
        has_history = bool(history and history.strip())
        follow_up = _is_follow_up(query, has_history)
        repeat = _is_repeat_question(query, history) if has_history else False

        previous_answer = ""
        if follow_up or repeat:
            previous_answer = _get_previous_answer(history)
            logger.info(
                "Detected %s — injecting anti-repetition prompt",
                "follow-up" if follow_up else "repeat question",
            )

        # Get appropriate prompt template
        template = get_prompt_for_role(user_role)

        # Format prompt (with follow-up instruction if applicable)
        prompt = format_prompt(
            template=template,
            question=query,
            context=context,
            grade=grade,
            subject=subject,
            include_analogy=include_analogy,
            include_realworld=include_realworld,
            history=history,
            previous_answer=previous_answer,
        )

        # Add system prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

        # Generate response
        try:
            response = await self.llm.generate(full_prompt)
        except Exception as e:
            logger.error("LLM generation failed: %s", e)
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
            logger.debug("Structured JSON parsed successfully")
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
            confidence = float(parsed.confidence)
            if not parsed.is_grounded or confidence < 0.3:
                sufficiency = "insufficient"
            elif confidence < 0.7:
                sufficiency = "partial"
            else:
                sufficiency = "sufficient"

            logger.info(
                "Structured response: grounded=%s, confidence=%.2f, citations_valid=%s",
                parsed.is_grounded,
                confidence,
                citations_valid,
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
        logger.warning(
            "Failed to parse structured output, using fallback. "
            "Response preview: %s...",
            response[:100],
        )
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

    def _extract_section(self, text: str, section_name: str) -> str | None:
        """Extract a section from the response."""
        import re

        pattern = rf"\*\*{section_name}.*?\*\*:?\s*(.*?)(?=\n\n\*\*|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None
