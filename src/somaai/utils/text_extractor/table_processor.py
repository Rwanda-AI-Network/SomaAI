"""Advanced table processing engine using DSA principles.

Implements graph-based normalization, tree-based header extraction,
and multi-representation serialization for RAG optimization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class CellNode:
    """Represents a single table cell with span and hierarchy info."""
    row: int
    col: int
    content: str
    row_span: int = 1
    col_span: int = 1
    cell_type: str = 'data'  # 'header', 'data', 'merged'
    parent_id: Optional[tuple[int, int]] = None
    
    @property
    def id(self) -> tuple[int, int]:
        return (self.row, self.col)


class UnionFind:
    """Union-Find for detecting merged cell regions."""
    
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
    
    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]
    
    def union(self, x: int, y: int):
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        
        # Union by rank
        if self.rank[px] < self.rank[py]:
            self.parent[px] = py
        elif self.rank[px] > self.rank[py]:
            self.parent[py] = px
        else:
            self.parent[py] = px
            self.rank[px] += 1


@dataclass
class Grid:
    """Normalized 2D grid with helper methods."""
    cells: list[list[Optional[CellNode]]]
    width: int
    height: int
    uf: UnionFind
    
    def __getitem__(self, pos: tuple[int, int]) -> Optional[CellNode]:
        r, c = pos
        if 0 <= r < self.height and 0 <= c < self.width:
            return self.cells[r][c]
        return None
    
    def is_valid(self, r: int, c: int) -> bool:
        return 0 <= r < self.height and 0 <= c < self.width
    
    def get_merged_owner(self, r: int, c: int) -> Optional[CellNode]:
        """Get the owning cell for a merged region."""
        cell = self[r, c]
        if cell and cell.parent_id:
            return self[cell.parent_id]
        return cell


class HeaderTreeNode:
    """Node in header hierarchy tree."""
    
    def __init__(self, content: str, level: int = 0):
        self.content = content
        self.level = level
        self.children: list[HeaderTreeNode] = []
        self.col_indices: list[int] = []
    
    def add_child(self, child: HeaderTreeNode):
        self.children.append(child)
    
    def get_path(self) -> str:
        """Get full header path (e.g., 'Q1 - Sales')."""
        parts = []
        node = self
        while node and node.content:
            parts.insert(0, node.content)
            node = getattr(node, 'parent', None)
        return ' - '.join(parts) if len(parts) > 1 else parts[0] if parts else ''


class TableNormalizer:
    """Converts irregular table data to normalized grid."""
    
    @staticmethod
    def normalize(raw_table: list[list[Any]]) -> Grid:
        """
        Normalize irregular table to uniform grid.
        
        Args:
            raw_table: Raw 2D list (may have None, irregular lengths)
            
        Returns:
            Normalized Grid with Union-Find for merged cells
        """
        if not raw_table:
            return Grid([], 0, 0, UnionFind(0))
        
        # Step 1: Determine dimensions
        height = len(raw_table)
        width = max(len(row) for row in raw_table) if raw_table else 0
        
        # Step 2: Initialize grid and Union-Find
        cells = [[None]*width for _ in range(height)]
        uf = UnionFind(height * width)
        
        # Step 3: Populate cells and detect merges
        for r, row in enumerate(raw_table):
            for c, value in enumerate(row):
                # Create cell node
                content = str(value) if value is not None else ''
                cells[r][c] = CellNode(
                    row=r,
                    col=c,
                    content=content.strip(),
                    cell_type='header' if r < 2 else 'data'  # Heuristic
                )
                
                # Detect horizontal merge (repeated values)
                if c > 0 and cells[r][c-1] and cells[r][c-1].content == content and content:
                    uf.union(r * width + c, r * width + (c - 1))
                    cells[r][c].parent_id = (r, c - 1)
                    cells[r][c-1].col_span += 1
                
                # Detect vertical merge
                if r > 0 and cells[r-1][c] and cells[r-1][c].content == content and content:
                    uf.union(r * width + c, (r - 1) * width + c)
                    cells[r][c].parent_id = (r - 1, c)
                    if cells[r-1][c].parent_id is None:
                        cells[r-1][c].row_span += 1
        
        return Grid(cells, width, height, uf)


class HeaderExtractor:
    """Extracts hierarchical header structure."""
    
    @staticmethod
    def build_header_tree(grid: Grid) -> dict[int, str]:
        """
        Build header tree and return column-to-path mapping.
        
        Args:
            grid: Normalized grid
            
        Returns:
            Dict mapping col_idx -> full header path
        """
        if grid.height < 1:
            return {}
        
        # Heuristic: Detect header row count
        header_row_count = HeaderExtractor._detect_header_rows(grid)
        
        # Build column paths
        col_paths = {}
        for col_idx in range(grid.width):
            path_parts = []
            seen = set()
            
            # Collect headers from top down
            for row_idx in range(header_row_count):
                cell = grid[row_idx, col_idx]
                if cell and cell.content and cell.content not in seen:
                    path_parts.append(cell.content)
                    seen.add(cell.content)
            
            # Smart fallback: Use content hints if no header found
            if not path_parts:
                col_name = HeaderExtractor._infer_column_name(grid, col_idx, header_row_count)
                col_paths[col_idx] = col_name
            else:
                col_paths[col_idx] = ' - '.join(path_parts)
        
        return col_paths
    
    @staticmethod
    def _infer_column_name(grid: Grid, col_idx: int, header_rows: int) -> str:
        """
        Infer meaningful column name from content when header is missing.
        
        Args:
            grid: Normalized grid
            col_idx: Column index
            header_rows: Number of header rows
            
        Returns:
            Inferred column name
        """
        # Strategy 1: Look at first few data values
        data_values = []
        for row_idx in range(header_rows, min(header_rows + 5, grid.height)):
            cell = grid[row_idx, col_idx]
            if cell and cell.content:
                data_values.append(cell.content)
        
        if not data_values:
            return f'Column_{col_idx}'  # Last resort
        
        # Strategy 2: Detect column type from content
        sample = data_values[0]
        
        # Check if it's numeric
        try:
            float(sample.replace(',', '').replace('$', '').replace('%', ''))
            # Check for currency
            if '$' in sample or '£' in sample or '€' in sample:
                return 'Amount'
            # Check for percentage
            elif '%' in sample:
                return 'Percentage'
            # Generic numeric
            else:
                return 'Value'
        except ValueError:
            pass
        
        # Check if it's a date
        if any(sep in sample for sep in ['/', '-', '.']):
            parts = sample.replace('/', '-').replace('.', '-').split('-')
            if len(parts) >= 2:
                try:
                    # Try to parse as date components
                    if all(p.isdigit() for p in parts[:2]):
                        return 'Date'
                except:
                    pass
        
        # Check if it's a name/identifier pattern
        if sample.replace(' ', '').isalpha():
            # First column is often entity name
            if col_idx == 0:
                return 'Name'
            else:
                return 'Category'
        
        # Check if it's an ID pattern
        if sample.replace('-', '').replace('_', '').isalnum() and len(sample) < 20:
            return 'ID'
        
        # Fallback: Use first word of first value as hint
        first_word = sample.split()[0] if sample else 'Column'
        return first_word.strip(',:;')[:15]  # Max 15 chars
    
    @staticmethod
    def _detect_header_rows(grid: Grid) -> int:
        """Detect number of header rows using heuristics."""
        if grid.height <= 2:
            return min(1, grid.height)
        
        # Heuristic: Header rows have higher uniqueness ratio
        for row_idx in range(min(4, grid.height)):
            row_cells = [grid[row_idx, c] for c in range(grid.width)]
            row_values = [c.content for c in row_cells if c and c.content]
            
            # If next row has significantly more unique values, current is last header
            if row_idx + 1 < grid.height:
                next_row_cells = [grid[row_idx + 1, c] for c in range(grid.width)]
                next_values = [c.content for c in next_row_cells if c and c.content]
                
                if len(set(next_values)) > len(set(row_values)) * 1.5:
                    return row_idx + 1
        
        return 2  # Default: first 2 rows


class RAGSerializer:
    """Serializes table to multiple RAG-optimized formats."""
    
    @staticmethod
    def serialize(grid: Grid, col_paths: dict[int, str]) -> dict[str, Any]:
        """
        Generate multiple representations for RAG.
        
        Returns:
            {
                'markdown': str,
                'rows': list[dict],
                'triples': list[dict],
                'metadata': dict
            }
        """
        header_row_count = len([r for r in range(grid.height) 
                                if grid[r, 0] and grid[r, 0].cell_type == 'header'])
        
        data_rows = []
        for r in range(header_row_count, grid.height):
            row_data = {}
            for c in range(grid.width):
                cell = grid[r, c]
                if cell:
                    row_data[col_paths.get(c, f'col_{c}')] = cell.content
            if any(row_data.values()):  # Skip empty rows
                data_rows.append(row_data)
        
        # Generate Markdown
        markdown = RAGSerializer._to_markdown(grid, col_paths, header_row_count)
        
        # Generate semantic triples
        triples = []
        for row in data_rows:
            entity = row.get(list(row.keys())[0], 'Unknown')  # First column as entity
            for key, value in list(row.items())[1:]:
                if value:
                    triples.append({
                        'subject': entity,
                        'predicate': key,
                        'object': value
                    })
        
        return {
            'markdown': markdown,
            'rows': data_rows,
            'triples': triples,
            'metadata': {
                'dimensions': (grid.height, grid.width),
                'header_depth': header_row_count,
                'data_row_count': len(data_rows)
            }
        }
    
    @staticmethod
    def _to_markdown(grid: Grid, col_paths: dict[int, str], header_rows: int) -> str:
        """Convert grid to Markdown table."""
        lines = []
        
        # Header
        header = '| ' + ' | '.join(col_paths.get(c, f'Col{c}') for c in range(grid.width)) + ' |'
        lines.append(header)
        
        # Separator
        separator = '|' + '|'.join('---' for _ in range(grid.width)) + '|'
        lines.append(separator)
        
        # Data rows
        for r in range(header_rows, grid.height):
            row_values = []
            for c in range(grid.width):
                cell = grid[r, c]
                content = cell.content if cell else ''
                row_values.append(content)
            
            if any(row_values):  # Skip empty rows
                lines.append('| ' + ' | '.join(row_values) + ' |')
        
        return '\n'.join(lines)


class AdvancedTableProcessor:
    """Main orchestrator for advanced table processing."""
    
    def process(self, raw_table: list[list[Any]]) -> dict[str, Any]:
        """
        Process raw table through full pipeline.
        
        Args:
            raw_table: Raw 2D list from pdfplumber or similar
            
        Returns:
            RAG-optimized representations
        """
        try:
            # Algorithm 1: Grid Normalization
            grid = TableNormalizer.normalize(raw_table)
            logger.debug(f"Normalized grid: {grid.height}x{grid.width}")
            
            # Algorithm 2: Header Extraction
            col_paths = HeaderExtractor.build_header_tree(grid)
            logger.debug(f"Extracted {len(col_paths)} column headers")
            
            # Algorithm 3: Propagate empty cells (already done in normalization)
            
            # Algorithm 4: RAG Serialization
            result = RAGSerializer.serialize(grid, col_paths)
            logger.info(f"Processed table: {result['metadata']}")
            
            return result
        
        except Exception as e:
            logger.error(f"Table processing failed: {e}")
            # Fallback: return simple markdown
            return {
                'markdown': self._fallback_markdown(raw_table),
                'rows': [],
                'triples': [],
                'metadata': {'error': str(e)}
            }
    
    def _fallback_markdown(self, raw_table: list[list[Any]]) -> str:
        """Simple fallback for failed processing."""
        if not raw_table:
            return ''
        
        lines = []
        for row in raw_table:
            line = '| ' + ' | '.join(str(cell or '') for cell in row) + ' |'
            lines.append(line)
        
        # Add separator after first row
        if len(lines) > 1:
            width = len(raw_table[0])
            sep = '|' + '|'.join('---' for _ in range(width)) + '|'
            lines.insert(1, sep)
        
        return '\n'.join(lines)
