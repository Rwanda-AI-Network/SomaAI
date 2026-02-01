"""Mock retriever for RAG testing."""

from somaai.modules.rag.mock_data import MOCK_CHUNKS
from somaai.modules.rag.types import RAGInput, RetrievedChunk


class MockRetriever:
    """Simple mock retriever using in-memory curriculum chunks."""

    def __init__(self, top_k: int = 3):
        """Initialize retriever.

        Args:
            top_k: Maximum number of chunks to retrieve
        """
        self.top_k = top_k

    async def retrieve(self, inp: RAGInput) -> list[RetrievedChunk]:
        """Retrieve relevant chunks from mock data.

        Args:
            inp: RAG input with query and filters

        Returns:
            List of retrieved chunks sorted by relevance score
        """
        # Filter by subject and grade
        filtered = [
            chunk
            for chunk in MOCK_CHUNKS
            if chunk["subject"] == inp.subject.value.lower()
            and chunk["grade"] == inp.grade.value
        ]

        # If no exact match, try subject only
        if not filtered:
            filtered = [
                chunk
                for chunk in MOCK_CHUNKS
                if chunk["subject"] == inp.subject.value.lower()
            ]

        # Score by naive keyword overlap
        scored_chunks = []
        import string
        
        def tokenize(text: str) -> set[str]:
            # Remove punctuation and split
            translator = str.maketrans("", "", string.punctuation)
            clean_text = text.lower().translate(translator)
            return set(clean_text.split())

        query_words = tokenize(inp.query)

        for chunk in filtered:
            content_words = tokenize(chunk["content"])
            overlap = len(query_words & content_words)
            score = min(overlap / max(len(query_words), 1), 1.0)

            if score > 0:
                scored_chunks.append((chunk, score))

        # Sort by score descending
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        # Take top_k
        top_chunks = scored_chunks[: self.top_k]

        # Convert to RetrievedChunk
        return [
            RetrievedChunk(
                chunk_id=None,  # Mock mode - no real chunk IDs
                doc_id=chunk["doc_id"],
                doc_title=chunk["doc_title"],
                page_start=chunk["page_start"],
                page_end=chunk["page_end"],
                snippet=chunk["content"],
                score=score,
            )
            for chunk, score in top_chunks
        ]
