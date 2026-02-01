"""Structured output schemas for LLM responses.

Provides Pydantic models for parsing and validating LLM outputs.
Uses Decimal for precise floating-point handling.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class CitationOutput(BaseModel):
    """Citation extracted from LLM response."""

    page_number: int = Field(..., description="Page number referenced")
    quote: str = Field(..., description="Quoted text from source")


class GroundedResponse(BaseModel):
    """Structured response with grounding verification.

    Forces the LLM to explicitly state whether the answer
    is grounded in the provided context.
    """

    answer: str = Field(..., description="The answer to the question")
    is_grounded: bool = Field(
        ...,
        description="True if answer is fully based on provided context"
    )
    confidence: Decimal = Field(
        ...,
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="Confidence score 0-1 (Decimal precision)"
    )
    citations: list[CitationOutput] = Field(
        default_factory=list,
        description="Page citations used in the answer"
    )
    reasoning: str = Field(
        "",
        description="Brief reasoning for the answer"
    )
    analogy: str | None = Field(
        None,
        description="Analogy to explain the concept (if requested)"
    )
    realworld_context: str | None = Field(
        None,
        description="Real-world application (if requested)"
    )


class InsufficientContextResponse(BaseModel):
    """Response when context is insufficient."""

    answer: str = Field(
        default=(
            "I don't have enough information in the curriculum "
            "to answer this question."
        ),
    )
    is_grounded: bool = Field(default=False)
    confidence: Decimal = Field(default=Decimal("0.0"))
    missing_info: str = Field(
        ...,
        description="What information is missing"
    )


# JSON schema for prompting
GROUNDED_RESPONSE_SCHEMA = """{
  "answer": "Your answer here",
  "is_grounded": true,
  "confidence": 0.85,  // Decimal value
  "citations": [
    {"page_number": 1, "quote": "relevant quote"}
  ],
  "reasoning": "Brief explanation"
}"""


def parse_grounded_response(text: str) -> GroundedResponse | None:
    """Parse LLM response to structured format.

    Attempts to extract JSON from the response.

    Args:
        text: Raw LLM response

    Returns:
        Parsed GroundedResponse or None if parsing fails
    """
    import json
    import re

    # Try to find JSON in response
    json_patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"\{[^{}]*\"answer\"[^{}]*\}",
    ]

    for pattern in json_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = match.group(1) if "```" in pattern else match.group(0)
                data = json.loads(json_str)
                return GroundedResponse(**data)
            except (json.JSONDecodeError, ValueError):
                continue

    # Fallback: create from unstructured response
    return None


def validate_citations(
    response: GroundedResponse,
    retrieved_docs: list[dict],
) -> tuple[bool, list[dict]]:
    """Validate that citations reference actual retrieved content.

    Args:
        response: Parsed LLM response
        retrieved_docs: Documents used as context

    Returns:
        Tuple of (all_valid, validated_citations)
    """
    validated = []
    all_valid = True

    # Get all page numbers from retrieved docs
    available_pages = set()
    for doc in retrieved_docs:
        meta = doc.get("metadata", {})
        page_start = meta.get("page_start", 0)
        page_end = meta.get("page_end", page_start)
        for p in range(page_start, page_end + 1):
            available_pages.add(p)

    for citation in response.citations:
        is_valid = citation.page_number in available_pages

        validated.append({
            "page_number": citation.page_number,
            "quote": citation.quote,
            "valid": is_valid,
        })

        if not is_valid:
            all_valid = False

    return all_valid, validated
