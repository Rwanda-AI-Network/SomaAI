from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Section:
    """Document hierarchy (H1, H2, H3) for semantic chunking."""

    level: int  # 1=H1, 2=H2, 3=H3
    title: str
    content: str
    start_page: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Table:
    """Extracted table in Markdown format for LLM reasoning."""

    markdown: str  # e.g., "| Name | Score |\n|---|---|\n| Alice | 95 |"
    caption: str | None
    page_number: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Page:
    """Page-level structure with metadata for precise citations."""

    page_number: int
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """RAG-optimized extraction result preserving document structure.

    Key improvements over flat text:
    - Hierarchy preserved via Section objects
    - Tables extracted in Markdown format
    - Page-level metadata for citations
    - Markdown output for LLM reasoning
    """

    full_text: str  # Markdown with headers/tables
    pages: list[Page]  # Page-by-page content
    hierarchy: list[Section] = field(default_factory=list)  # Document outline
    tables: list[Table] = field(default_factory=list)  # Extracted tables
    metadata: dict = field(default_factory=dict)  # Global doc metadata


class BaseExtractionStrategy(ABC):
    """Abstract base class for text extraction strategies."""

    @abstractmethod
    def extract(self, file_stream, language: str = "eng") -> ExtractionResult:
        """
        Extracts text from the given file stream.

        Args:
            file_stream: A binary file stream (e.g. from open() or st.file_uploader)
            language: Language code for OCR or specific parsing (default: 'eng')

        Returns:
            ExtractionResult object containing the text and metadata.
        """
        pass
