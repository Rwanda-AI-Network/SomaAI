"""Document service for document management."""

from somaai.contracts.docs import DocumentResponse, DocumentViewLinkResponse


class DocumentService:
    """Service for document operations.

    Handles document retrieval and page viewing.
    Document ingestion is handled by the ingest module.
    """

    async def get_document(self, doc_id: str) -> DocumentResponse | None:
        """Get document metadata by ID.

        Args:
            doc_id: Document identifier

        Returns:
            Document metadata or None if not found
        """
        pass

    async def get_document_page(
        self,
        doc_id: str,
        page_number: int,
    ) -> DocumentViewLinkResponse | None:
        """Get a specific page from a document.

        Args:
            doc_id: Document identifier
            page_number: Page number (1-indexed)

        Returns:
            Page content/image or None if not found

        Content:
            - For PDFs: Returns image_url for rendered page
            - For text docs: Returns text content
        """
        pass

    async def list_documents(
        self,
        grade: str | None = None,
        subject: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List documents with optional filters.

        Args:
            grade: Filter by grade
            subject: Filter by subject
            page: Page number
            page_size: Items per page

        Returns:
            Paginated list of documents
        """
        pass

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its chunks.

        Args:
            doc_id: Document identifier

        Returns:
            True if deleted, False if not found

        Cleanup:
            - Removes document from DB
            - Removes chunks from vector DB
            - Removes file from storage
        """
        pass
