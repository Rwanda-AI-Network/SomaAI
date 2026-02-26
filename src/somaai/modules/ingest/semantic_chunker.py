"""Semantic chunking module for RAG-optimized document chunking.

Chunks by semantic boundaries (sections, tables) instead of character count.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from somaai.utils.ids import generate_id

if TYPE_CHECKING:
    from somaai.utils.text_extractor import ExtractionResult, Page, Section, Table

logger = logging.getLogger(__name__)


class SemanticChunker:
    """Chunks documents by semantic boundaries for better RAG performance."""

    def __init__(self, max_chunk_size: int = 1500, overlap_size: int = 200):
        """
        Initialize semantic chunker.

        Args:
            max_chunk_size: Maximum characters per chunk (soft limit)
            overlap_size: Overlap character count for context preservation

        Args:
            max_chunk_size: Maximum characters per chunk (soft limit)
            overlap_size: Overlap character count for context preservation
        """
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

        # Use LangChain's battle-tested splitter for text
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=overlap_size,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator=False,
        )

    def chunk(
        self, extraction: ExtractionResult, base_metadata: dict[str, Any]
    ) -> list[Document]:
        """
        Main chunking method.

        Strategy:
        1. If hierarchy exists -> chunk by sections
        2. Otherwise -> chunk by pages
        3. Always isolate tables as separate chunks

        Args:
            extraction: ExtractionResult from text_extractor
            base_metadata: Common metadata (doc_id, grade, subject, etc.)

        Returns:
            List of LangChain Documents
        """

        chunks: list[Document] = []

        # Strategy 1: Chunk by sections (preferred)
        if extraction.hierarchy:
            logger.info(f"Chunking {len(extraction.hierarchy)} sections")
            chunks.extend(self._chunk_sections(extraction.hierarchy, base_metadata))
        else:
            # Fallback: Chunk by pages
            logger.info(
                f"No hierarchy detected, chunking {len(extraction.pages)} pages"
            )
            chunks.extend(self._chunk_pages(extraction.pages, base_metadata))

        # Strategy 2: Isolate tables as atomic chunks
        if extraction.tables:
            logger.info(f"Isolating {len(extraction.tables)} tables")
            chunks.extend(self._chunk_tables(extraction.tables, base_metadata))

        logger.info(f"Created {len(chunks)} semantic chunks")
        return chunks

    def _chunk_sections(
        self, sections: list[Section], base_metadata: dict[str, Any]
    ) -> list[Document]:
        """
        Chunk by section boundaries.

        Args:
            sections: List of Section objects from hierarchy
            base_metadata: Common metadata

        Returns:
            List of Document chunks
        """

        chunks = []

        for section in sections:
            # Build section path for context
            section_path = [section.title]

            content = section.content.strip()
            if not content:
                continue

            # If section is small enough, keep as single chunk
            if len(content) <= self.max_chunk_size:
                chunks.append(
                    Document(
                        page_content=content,
                        metadata={
                            **base_metadata,
                            "chunk_type": "section",
                            "section_title": section.title,
                            "section_level": section.level,
                            "section_path": section_path,
                            "page": getattr(section, "start_page", 1),
                            "has_structure": True,
                        },
                    )
                )
            else:
                # Split large section at paragraph boundaries
                chunks.extend(
                    self._split_large_section(section, section_path, base_metadata)
                )

        return chunks

    def _split_large_section(
        self, section: Section, section_path: list[str], base_metadata: dict[str, Any]
    ) -> list[Document]:
        """
        Split large section while preserving context.

        Args:
            section: Section object
            section_path: Hierarchical path (e.g., ["Chapter 3", "3.1"])
            base_metadata: Common metadata

        Returns:
            List of sub-chunks
        """

        chunks = []

        # 1. Create Parent Chunk (Full Context)
        parent_id = generate_id()
        # Embed context
        contextual_content = f"{section.title}\n\n{section.content.strip()}"
        chunks.append(
            Document(
                page_content=contextual_content,
                metadata={
                    **base_metadata,
                    **base_metadata,
                    "chunk_id": parent_id,
                    "chunk_type": "section_parent",
                    "section_title": section.title,
                    "section_level": section.level,
                    "section_path": section_path,
                    "page": getattr(section, "start_page", 1),
                    "is_parent": True,
                    "has_structure": True,
                },
            )
        )

        # 2. Split content using LangChain splitter (handles overlap and separators)
        # We split the raw content, then prepend context to each chunk
        text_chunks = self.text_splitter.split_text(section.content.strip())

        for i, text_chunk in enumerate(text_chunks):
            # Embed context for vector search
            # Note: We do this AFTER splitting to ensure the split is based
            # on content size, but we prepend the title so the vector
            # model sees it. This might slightly exceed max_chunk_size,
            # which is acceptable for metadata.
            contextual_text = f"{section.title}\n\n{text_chunk}"

            chunks.append(
                Document(
                    page_content=contextual_text,
                    metadata={
                        **base_metadata,
                        "chunk_type": "section_fragment",
                        "section_title": section.title,
                        "section_level": section.level,
                        "section_path": section_path,
                        "is_continuation": i > 0,
                        "fragment_index": i,
                        "page": getattr(section, "start_page", 1),
                        "has_structure": True,
                        "parent_id": parent_id,
                        "is_child": True,
                    },
                )
            )

        return chunks

    def _chunk_tables(
        self, tables: list[Table], base_metadata: dict[str, Any]
    ) -> list[Document]:
        """
        Isolate tables as atomic chunks.

        Tables should NEVER be fragmented - they're kept whole
        to preserve structure for LLM reasoning.

        Args:
            tables: List of Table objects
            base_metadata: Common metadata

        Returns:
            List of table chunks
        """
        from langchain_core.documents import Document

        chunks = []

        for table in tables:
            # Add contextual prefix
            context_lines = [f"Table from page {table.page_number}"]
            if table.caption:
                context_lines.append(f"Caption: {table.caption}")

            context = "\n".join(context_lines)
            content = f"{context}\n\n{table.markdown}"

            # Extract table metadata
            table_meta = table.metadata or {}

            chunks.append(
                Document(
                    page_content=content,
                    metadata={
                        **base_metadata,
                        "chunk_type": "table",
                        "page": table.page_number,
                        "table_caption": table.caption,
                        "table_dimensions": table_meta.get("dimensions"),
                        "has_merged_cells": table_meta.get("has_merged_cells", False),
                        "data_row_count": table_meta.get("data_row_count", 0),
                        "has_structure": True,
                    },
                )
            )

        return chunks

    def _chunk_pages(
        self, pages: list[Page], base_metadata: dict[str, Any]
    ) -> list[Document]:
        """
        Fallback: Chunk by pages when no structure detected.

        Args:
            pages: List of Page objects
            base_metadata: Common metadata

        Returns:
            List of page chunks
        """
        from langchain_core.documents import Document

        chunks = []

        for page in pages:
            content = page.content.strip()
            if not content:
                continue

            # If page fits in one chunk
            if len(content) <= self.max_chunk_size:
                chunks.append(
                    Document(
                        page_content=content,
                        metadata={
                            **base_metadata,
                            "chunk_type": "page",
                            "page": page.page_number,
                            "has_structure": False,
                        },
                    )
                )
            else:
                # Split large page at paragraph boundaries
                chunks.extend(self._split_large_page(page, base_metadata))

        return chunks

    def _split_large_page(
        self, page: Page, base_metadata: dict[str, Any]
    ) -> list[Document]:
        """Split large page into fragments."""
        from langchain_core.documents import Document

        chunks = []

        # 1. Create Parent Chunk (Full Context)
        parent_id = generate_id()
        chunks.append(
            Document(
                page_content=page.content.strip(),
                metadata={
                    **base_metadata,
                    "chunk_id": parent_id,
                    "chunk_type": "page_parent",
                    "page": page.page_number,
                    "has_structure": False,
                    "is_parent": True,
                },
            )
        )

        # 2. Split using LangChain
        text_chunks = self.text_splitter.split_text(page.content.strip())

        for i, text_chunk in enumerate(text_chunks):
            chunks.append(
                Document(
                    page_content=text_chunk,
                    metadata={
                        **base_metadata,
                        "chunk_type": "page_fragment",
                        "page": page.page_number,
                        "fragment_index": i,
                        "has_structure": False,
                        "parent_id": parent_id,
                        "is_child": True,
                    },
                )
            )

        return chunks
