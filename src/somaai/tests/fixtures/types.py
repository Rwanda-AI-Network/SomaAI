"""RAG pipeline types and data structures."""

from __future__ import annotations

from dataclasses import dataclass

from somaai.contracts.common import GradeLevel, Subject, UserRole


@dataclass(frozen=True)
class RAGInput:
    """Input for RAG pipeline execution."""

    query: str
    grade: GradeLevel
    subject: Subject
    user_role: UserRole
    teaching_classes: list[GradeLevel] | None = None
    enable_analogy: bool = False
    enable_realworld: bool = False
    history: str = ""


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk retrieved from the knowledge base."""

    chunk_id: str | None
    doc_id: str
    doc_title: str
    page_start: int
    page_end: int
    snippet: str
    score: float


@dataclass(frozen=True)
class RAGResult:
    """Result from RAG pipeline execution."""

    answer: str
    sufficiency: str  # must be "sufficient" or "insufficient"
    retrieved_chunks: list[RetrievedChunk]
    analogy: str | None = None
    realworld_context: str | None = None
