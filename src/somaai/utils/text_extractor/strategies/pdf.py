"""Enhanced PDF extraction strategy using pdfplumber for RAG.

Extracts:
- Hierarchical structure (via font size analysis)
- Tables in Markdown format (with advanced processing)
- Page-level metadata
"""

import logging
import re
from io import BytesIO

import pdfplumber

from ..exceptions import TextExtractionError
from ..table_processor import AdvancedTableProcessor
from .base import BaseExtractionStrategy, ExtractionResult, Page, Section, Table

logger = logging.getLogger(__name__)


class PdfStructuredStrategy(BaseExtractionStrategy):
    """RAG-optimized PDF extraction with hierarchy and advanced table support."""

    def __init__(self):
        self.table_processor = AdvancedTableProcessor()

    def extract(self, file_stream, language: str = "eng") -> ExtractionResult:
        logger.info("Starting structured PDF extraction with pdfplumber.")
        try:
            if hasattr(file_stream, "seek"):
                file_stream.seek(0)

            # Read into memory for pdfplumber
            pdf_bytes = file_stream.read()
            pdf_file = BytesIO(pdf_bytes)

            pages_data = []
            all_tables = []
            hierarchy = []
            full_text_parts = []

            with pdfplumber.open(pdf_file) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract text
                    page_text = page.extract_text() or ""

                    # Extract tables with enhanced settings for complex structures
                    tables = page.extract_tables(
                        table_settings={
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "lines",
                            "snap_tolerance": 3,
                            "join_tolerance": 3,
                            "edge_min_length": 3,
                            "intersection_tolerance": 3,
                        }
                    )
                    for table_idx, table_data in enumerate(tables):
                        if table_data:
                            # Use advanced DSA-based processor
                            processed = self.table_processor.process(table_data)
                            markdown_table = processed["markdown"]

                            all_tables.append(
                                Table(
                                    markdown=markdown_table,
                                    caption=None,
                                    page_number=page_num,
                                    metadata={
                                        "table_index": table_idx,
                                        **processed["metadata"],
                                    },
                                )
                            )

                            # Insert table reference in text
                            page_text += f"\n\n{markdown_table}\n\n"

                    # Create Page object
                    pages_data.append(
                        Page(
                            page_number=page_num,
                            content=page_text,
                            metadata={"has_tables": len(tables) > 0},
                        )
                    )

                    full_text_parts.append(page_text)

                # Extract hierarchy (simple heuristic via headings detection)
                hierarchy = self._extract_hierarchy(pages_data)

            full_text = "\n\n".join(full_text_parts)

            logger.info(
                f"Structured PDF extraction complete: "
                f"{len(pages_data)} pages, {len(all_tables)} tables, "
                f"{len(hierarchy)} sections"
            )

            return ExtractionResult(
                full_text=full_text,
                pages=pages_data,
                hierarchy=hierarchy,
                tables=all_tables,
                metadata={
                    "method": "pdfplumber_structured",
                    "page_count": len(pages_data),
                    "table_count": len(all_tables),
                    "section_count": len(hierarchy),
                },
            )

        except Exception as e:
            logger.error(f"Structured PDF extraction failed: {e}")
            raise TextExtractionError(f"Failed to extract PDF: {str(e)}")

    def _process_hierarchical_table(self, table_data: list[list]) -> list[list]:
        """Process tables with merged cells and sub-columns.

        Handles cases like:
        | Category | Q1          | Q2          |
        |          | Sales | Cost | Sales | Cost |

        Args:
            table_data: Raw table data from pdfplumber

        Returns:
            Processed table with propagated merged cell values
        """
        if not table_data or len(table_data) < 2:
            return table_data

        # Make a deep copy to avoid mutating original
        processed = [row[:] for row in table_data]

        # Step 1: Propagate merged cells vertically (copy from row above)
        for row_idx in range(len(processed)):
            for col_idx in range(len(processed[row_idx])):
                cell = processed[row_idx][col_idx]

                # If cell is empty/None, look up for parent value
                if not cell or (isinstance(cell, str) and cell.strip() == ""):
                    for up_idx in range(row_idx - 1, -1, -1):
                        if up_idx < len(processed) and col_idx < len(processed[up_idx]):
                            parent_cell = processed[up_idx][col_idx]
                            if parent_cell and (
                                not isinstance(parent_cell, str) or parent_cell.strip()
                            ):
                                processed[row_idx][col_idx] = parent_cell
                                break

        # Step 2: Propagate merged cells horizontally (copy from left)
        for row_idx in range(len(processed)):
            for col_idx in range(len(processed[row_idx])):
                cell = processed[row_idx][col_idx]

                if not cell or (isinstance(cell, str) and cell.strip() == ""):
                    for left_idx in range(col_idx - 1, -1, -1):
                        left_cell = processed[row_idx][left_idx]
                        if left_cell and (
                            not isinstance(left_cell, str) or left_cell.strip()
                        ):
                            processed[row_idx][col_idx] = left_cell
                            break

        # Step 3: Detect and combine multi-level headers
        # Check if first 2-3 rows look like hierarchical headers
        has_hierarchy = False
        if len(processed) >= 3:
            # Heuristic: If many cells in row 2 are empty/repeated,
            # it's likely hierarchical
            row1_unique = set(c for c in processed[0] if c)
            row2_unique = set(c for c in processed[1] if c)

            if len(row2_unique) > len(row1_unique) * 1.5:
                has_hierarchy = True

        if has_hierarchy and len(processed) >= 2:
            # Combine first two rows into single header
            combined_header = []
            for col_idx in range(len(processed[0])):
                parts = []
                for row_idx in range(2):
                    if col_idx < len(processed[row_idx]):
                        cell = processed[row_idx][col_idx]
                        if cell and isinstance(cell, str) and cell.strip():
                            parts.append(cell.strip())

                # Combine with separator, remove duplicates
                unique_parts = []
                for part in parts:
                    if part not in unique_parts:
                        unique_parts.append(part)

                combined_header.append(" - ".join(unique_parts) if unique_parts else "")

            # Return combined header + data rows
            return [combined_header] + processed[2:]

        return processed

    def _table_to_markdown(self, table_data: list[list]) -> str:
        """Convert table data to Markdown format.

        Args:
            table_data: 2D list of table cells

        Returns:
            Markdown table string
        """
        if not table_data or len(table_data) < 2:
            return ""

        # Build markdown table
        lines = []

        # Header row
        header = table_data[0]
        lines.append("| " + " | ".join(str(cell or "") for cell in header) + " |")

        # Separator
        lines.append("|" + "|".join("---" for _ in header) + "|")

        # Data rows
        for row in table_data[1:]:
            lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")

        return "\n".join(lines)

    def _extract_hierarchy(self, pages: list[Page]) -> list[Section]:
        """Extract document hierarchy from pages.

        Uses simple heuristic: lines in ALL CAPS or numbered (1., 1.1, etc.)

        Args:
            pages: List of Page objects

        Returns:
            List of Section objects
        """
        sections = []
        current_section_content = []
        current_section = None

        for page in pages:
            lines = page.content.split("\n")

            for line in lines:
                stripped = line.strip()

                # Skip empty lines
                if not stripped:
                    continue

                # Detect heading patterns
                is_heading, level, title = self._is_heading(stripped)

                if is_heading:
                    # Save previous section
                    if current_section:
                        current_section.content = "\n".join(
                            current_section_content
                        ).strip()
                        sections.append(current_section)

                    # Start new section
                    current_section = Section(
                        level=level,
                        title=title,
                        content="",
                        start_page=page.page_number,
                    )
                    current_section_content = []
                else:
                    if current_section:
                        current_section_content.append(line)

        # Save last section
        if current_section:
            current_section.content = "\n".join(current_section_content).strip()
            sections.append(current_section)

        return sections

    # def _is_heading(self, line: str) -> tuple[bool, int, str]:
    #     """Detect if line is a heading.

    #     Args:
    #         line: Text line

    #     Returns:
    #         (is_heading, level, title)
    #     """
    #     # Pattern 1: ALL CAPS (likely H1)
    #     if line.isupper() and len(line) > 3 and len(line) < 100:
    #         return True, 1, line

    #     # Pattern 2: Numbered (1., 1.1, 1.1.1)
    #     numbered_pattern = r'^(\d+(?:\.\d+)*)\.\s+(.+)$'
    #     match = re.match(numbered_pattern, line)
    #     if match:
    #         numbering = match.group(1)
    #         title = match.group(2)
    #         level = numbering.count('.') + 1
    #         return True, min(level, 3), title

    #     # Pattern 3: Chapter/Section keywords
    #     chapter_pattern = r'^(Chapter|Section|Part|Unit)\s+(\d+):?\s*(.*)$'
    #     match = re.match(chapter_pattern, line, re.IGNORECASE)
    #     if match:
    #         return True, 1, line

    #     return False, 0, ""

    def _is_heading(self, line: str) -> tuple[bool, int, str]:
        """Detect if line is a heading.

        Args:
            line: Text line

        Returns:
            (is_heading, level, title)
        """
        # Guard: reject lines that look like garbage/corrupted text
        # A real heading should be mostly alphanumeric with spaces
        if not self._looks_like_readable_text(line):
            return False, 0, ""

        # Pattern 1: ALL CAPS (likely H1)
        if line.isupper() and len(line) > 3 and len(line) < 100:
            return True, 1, line

        # Pattern 2: Numbered (1., 1.1, 1.1.1)
        numbered_pattern = r"^(\d+(?:\.\d+)*)\.\s+(.+)$"
        match = re.match(numbered_pattern, line)
        if match:
            numbering = match.group(1)
            title = match.group(2)
            level = numbering.count(".") + 1
            return True, min(level, 3), title

        # Pattern 3: Chapter/Section keywords
        chapter_pattern = r"^(Chapter|Section|Part|Unit)\s+(\d+):?\s*(.*)$"
        match = re.match(chapter_pattern, line, re.IGNORECASE)
        if match:
            return True, 1, line

        return False, 0, ""

    def _looks_like_readable_text(self, text: str) -> bool:
        """Check if text looks like actual readable content, not garbled output.

        Guards heading detection from matching garbage like 'GSSOR(' or
        '| | DCE | | DCE | |' as section headers.

        Args:
            text: Text to check

        Returns:
            True if text appears to be readable
        """
        stripped = text.strip()
        if not stripped or len(stripped) < 2:
            return False

        # Must contain at least one letter
        alpha_count = sum(1 for c in stripped if c.isalpha())
        if alpha_count == 0:
            return False

        # Alphanumeric ratio should be reasonable (>60%)
        # Rejects lines like "| | DCE | | DCE | |" (mostly pipes and spaces)
        alnum_count = sum(1 for c in stripped if c.isalnum())
        alnum_ratio = alnum_count / len(stripped)
        if alnum_ratio < 0.6:
            return False

        # For short lines (potential headings), check for minimum word count
        # Rejects single-token garbage like "'GSSOR("
        # But allows short valid headings like "INTRODUCTION" (1 word is fine if clean)
        words = stripped.split()
        if len(words) == 1:
            word = words[0]
            # Single word: must be purely alphabetic (no special chars mixed in)
            # "INTRODUCTION" → ok, "'GSSOR(" → rejected
            if not word.isalpha():
                return False

        return True
