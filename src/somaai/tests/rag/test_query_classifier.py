"""Tests for query classifier."""

import pytest

from somaai.modules.rag.query_classifier import classify_query


class TestClassifyQuery:
    """Test query classification — curriculum vs chitchat."""

    # ── Chitchat: should be caught ──────────────────────────────────

    @pytest.mark.parametrize(
        "query",
        [
            "hi",
            "Hello",
            "HEY",
            "hello!",
            "good morning",
            "Good Evening",
            "muraho",
            "amakuru",
            "bite",
        ],
    )
    def test_greetings_classified_as_chitchat(self, query: str) -> None:
        category, response = classify_query(query)
        assert category == "chitchat", f"'{query}' should be chitchat"
        assert response is not None

    @pytest.mark.parametrize(
        "query",
        ["thanks", "Thank you", "merci", "murakoze", "thx!"],
    )
    def test_gratitude_classified_as_chitchat(self, query: str) -> None:
        category, response = classify_query(query)
        assert category == "chitchat", f"'{query}' should be chitchat"
        assert response is not None
        assert "welcome" in response.lower() or "help" in response.lower()

    @pytest.mark.parametrize(
        "query",
        ["bye", "goodbye", "see you", "later"],
    )
    def test_farewells_classified_as_chitchat(self, query: str) -> None:
        category, response = classify_query(query)
        assert category == "chitchat", f"'{query}' should be chitchat"
        assert response is not None

    @pytest.mark.parametrize(
        "query",
        ["who are you", "what are you", "Who are you?"],
    )
    def test_identity_classified_as_chitchat(self, query: str) -> None:
        category, response = classify_query(query)
        assert category == "chitchat", f"'{query}' should be chitchat"
        assert response is not None
        assert "SomaAI" in response

    # ── Curriculum: should NOT be caught ─────────────────────────────

    @pytest.mark.parametrize(
        "query",
        [
            "What is process scheduling?",
            "Explain first come first served",
            "What are scheduling queues all about?",
            "Define a process in operating systems",
            "Hi, what are scheduling queues?",
            "Thanks, but what about FCFS?",
            "hello can you explain photosynthesis",
            "What is RAM?",
            "What is CPU?",
        ],
    )
    def test_curriculum_queries_not_caught(self, query: str) -> None:
        category, response = classify_query(query)
        assert category == "curriculum", f"'{query}' should be curriculum"
        assert response is None

    # ── Edge cases ──────────────────────────────────────────────────

    def test_empty_query_is_curriculum(self) -> None:
        """Empty queries pass through to the pipeline
        where input validation catches them."""
        category, _ = classify_query("")
        assert category == "curriculum"

    def test_whitespace_only_is_curriculum(self) -> None:
        category, _ = classify_query("   ")
        assert category == "curriculum"

    def test_single_word_question_is_curriculum(self) -> None:
        """Short but valid questions should pass through."""
        category, _ = classify_query("photosynthesis?")
        assert category == "curriculum"

    def test_long_greeting_with_question_is_curriculum(self) -> None:
        """Greetings mixed with questions should pass to RAG."""
        category, _ = classify_query(
            "Hello teacher, I want to understand the concept of scheduling"
        )
        assert category == "curriculum"
