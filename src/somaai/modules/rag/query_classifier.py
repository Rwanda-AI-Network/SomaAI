"""Lightweight query classifier to skip RAG for non-questions.

Classifies user input as 'curriculum' (needs RAG) or 'chitchat'
(greetings, gratitude, farewells — respond directly without retrieval).

Design: Regex-based for zero latency and no dependencies.
Conservative: Only catches pure chitchat. If in doubt, defaults to 'curriculum'.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ── Chitchat patterns (checked case-insensitively) ──────────────────────
# Each tuple: (compiled regex, response category)
# Patterns only match SHORT inputs (≤6 words) to avoid false positives
# on questions like "Hi, what are scheduling queues?"

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Greetings (simple or compound like "yoo how are you bro")
    (
        re.compile(
            r"^(hi+|hello|hey+|good\s*(morning|afternoon|evening|night)"
            r"|howdy|yo+|sup|what'?s\s*up|hola|salut|bonjour"
            r"|muraho|amakuru|umezute|bite"
            r"|hii+\s+wassup"
            r"|how\s+(are|r)\s+(you|u|ya))"
            r"(\s+(how\s+(are|r)\s+(you|u|ya)))?"
            r"(\s+(bro+|ma\s*g(ee|ie)?|man|guys?|fam|dude))?s*[!?.]*$",
            re.IGNORECASE,
        ),
        "greeting",
    ),
    # Gratitude
    (
        re.compile(
            r"^(thanks?|thank\s*you|thx|merci|murakoze"
            r"|appreciate\s*it)\s*[!?.]*$",
            re.IGNORECASE,
        ),
        "gratitude",
    ),
    # Farewells
    (
        re.compile(
            r"^(bye+|goodbye|see\s*(you|ya)|later|good\s*night"
            r"|mwiriwe|peace\s*out|take\s*care)"
            r"(\s+(bro+|man|guys?|fam))?\s*[!?.]*$",
            re.IGNORECASE,
        ),
        "farewell",
    ),
    # Identity questions about the bot
    (
        re.compile(
            r"^(who|what)\s+(are|r)\s+you\s*[!?.]*$",
            re.IGNORECASE,
        ),
        "identity",
    ),
    # Help requests (no subject specified)
    (
        re.compile(
            r"^(help|help\s+me|what\s+can\s+you\s+do)\s*[!?.]*$",
            re.IGNORECASE,
        ),
        "meta",
    ),
]

# Direct responses for each category
_RESPONSES: dict[str, str] = {
    "greeting": (
        "Hello! 👋 I'm SomaAI, your curriculum learning assistant. "
        "Ask me any question about your subjects and I'll help you "
        "understand the material. What would you like to learn about?"
    ),
    "gratitude": (
        "You're welcome! 😊 Feel free to ask more questions "
        "anytime. I'm here to help you learn."
    ),
    "farewell": (
        "Goodbye! 👋 Good luck with your studies. Come back anytime you need help!"
    ),
    "identity": (
        "I'm SomaAI, an AI learning assistant designed for Rwandan "
        "students and teachers. I answer questions based on your "
        "curriculum textbooks. Try asking me about any subject!"
    ),
    "meta": (
        "I can help you understand your curriculum! Ask me a question "
        "about any subject — Mathematics, Computer Science, English, "
        "and more. Specify your grade level for targeted answers."
    ),
}


def classify_query(query: str) -> tuple[str, str | None]:
    """Classify a query as 'curriculum' or 'chitchat'.

    Conservative design: only catches pure chitchat (short, obvious
    non-questions). Anything ambiguous is treated as curriculum.

    Args:
        query: Cleaned user query

    Returns:
        Tuple of (category, direct_response).
        - ('curriculum', None) → needs RAG pipeline
        - ('chitchat', response_text) → skip RAG, return directly
    """
    cleaned = query.strip()

    # Only classify short inputs as chitchat (≤6 words).
    # Longer inputs almost always contain a real question.
    word_count = len(cleaned.split())
    if word_count > 6:
        return "curriculum", None

    # Check against patterns
    for pattern, category in _PATTERNS:
        if pattern.match(cleaned):
            logger.info(
                "Query classified as chitchat (%s): '%s'",
                category,
                cleaned[:50],
            )
            return "chitchat", _RESPONSES[category]

    # Default: treat as curriculum question
    return "curriculum", None
