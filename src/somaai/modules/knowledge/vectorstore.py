"""Vector store interface. - we are using qdrant"""

from abc import ABC, abstractmethod


class VectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    async def add(self, texts: list[str], embeddings: list[list[float]]) -> None:
        """Add documents to the store."""
        pass

    @abstractmethod
    async def search(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        """Search for similar documents."""
        pass

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete documents from the store."""
        pass
