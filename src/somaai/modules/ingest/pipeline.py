"""Document ingestion pipeline using LangChain.

Processes curriculum documents (PDF, DOCX) into searchable chunks.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from somaai.utils.ids import generate_id

if TYPE_CHECKING:
    from somaai.settings import Settings


class IngestPipeline:
    """Document ingestion pipeline with LangChain.

    Supports:
    - PDF and DOCX document parsing
    - Semantic chunking with metadata
    - Embedding and storage in Qdrant
    - Progress tracking for background jobs
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize pipeline.

        Args:
            settings: Application settings
        """
        self._settings = settings
        self._splitter = None
        self._store = None

    @property
    def settings(self):
        """Get settings."""
        if self._settings is None:
            from somaai.settings import settings
            self._settings = settings
        return self._settings

    @property
    def splitter(self):
        """Get text splitter."""
        if self._splitter is None:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=[
                    "\n## ",       # Major headings
                    "\n### ",      # Subheadings
                    "\n#### ",     # Sub-subheadings
                    "\n\n",        # Paragraphs
                    "\n• ",        # Bullet points
                    "\n- ",        # List items
                    ". ",          # Sentences
                    " ",           # Words
                    "",            # Characters
                ],
                length_function=len,
            )
        return self._splitter

    @property
    def store(self):
        """Get Qdrant store."""
        if self._store is None:
            from somaai.modules.knowledge.stores.qdrant import QdrantStore
            self._store = QdrantStore(self.settings)
        return self._store

    def _get_loader(self, file_path: Path):
        """Get appropriate document loader based on file extension.

        Args:
            file_path: Path to the document

        Returns:
            LangChain document loader
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            # Prefer PyMuPDF for better encoding handling
            try:
                from langchain_community.document_loaders import PyMuPDFLoader
                return PyMuPDFLoader(str(file_path))
            except ImportError:
                from langchain_community.document_loaders import PyPDFLoader
                return PyPDFLoader(str(file_path))
        elif suffix == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader
            return Docx2txtLoader(str(file_path))
        elif suffix == ".txt":
            from langchain_community.document_loaders import TextLoader
            return TextLoader(str(file_path))
        elif suffix == ".md":
            from langchain_community.document_loaders import UnstructuredMarkdownLoader
            return UnstructuredMarkdownLoader(str(file_path))
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    async def run(
        self,
        doc_id: str,
        file_path: str,
        grade: str,
        subject: str,
        title: str | None = None,
        on_progress: Callable[[str, int], None] | None = None,
        skip_if_exists: bool = True,
    ) -> dict:
        """Execute the ingestion pipeline.

        Args:
            doc_id: Unique document identifier
            file_path: Path to the document file
            grade: Grade level (e.g., "S1", "P6")
            subject: Subject (e.g., "mathematics")
            title: Optional document title
            on_progress: Progress callback (stage, percentage)
            skip_if_exists: If True, skip ingestion if document already exists

        Returns:
            Dict with status, chunks count, and pages count
        """
        from somaai.utils.files import async_read_file, compute_file_hash

        path = Path(file_path)
        title = title or path.stem

        try:
            # Phase 0: Compute file hash for deduplication
            self._progress(on_progress, "Checking for duplicates", 0)
            file_content = await async_read_file(path)
            file_hash = compute_file_hash(file_content)

            # Check if this exact document already exists in vector store
            if skip_if_exists and await self.store.exists_by_doc_id(doc_id):
                self._progress(on_progress, "Document already exists", 100)
                return {
                    "status": "skipped",
                    "doc_id": doc_id,
                    "reason": "Document already ingested",
                    "file_hash": file_hash,
                }

            # Phase 1: Load document (0-20%)
            self._progress(on_progress, "Loading document", 5)
            if path.suffix.lower() == ".pdf":
                self._progress(on_progress, "PDF detected. Using forced OCR...", 10)
                try:
                    pages = self._load_with_ocr(path)
                    self._progress(on_progress, "OCR Complete", 20)
                except Exception as e:
                    self._progress(on_progress, f"OCR Failed: {e}. Fallback to standard loader.", 10)
                    loader = self._get_loader(path)
                    pages = loader.load()
            else:
                loader = self._get_loader(path)
                pages = loader.load()

            self._progress(on_progress, "Document loaded", 20)

            # Phase 2: Split into chunks (20-40%)
            self._progress(on_progress, "Creating chunks", 20)
            chunks = self.splitter.split_documents(pages)
            self._progress(on_progress, f"Created {len(chunks)} chunks", 30)

            # Phase 2.5: Filter low-quality chunks (30-40%)
            self._progress(on_progress, "Filtering low-quality chunks", 30)
            from somaai.modules.ingest.quality import filter_chunks
            chunks = filter_chunks(
                chunks,
                min_length=50,
                min_quality=0.3,
                remove_boilerplate=True,
            )
            self._progress(on_progress, f"{len(chunks)} quality chunks", 40)
            


            # Phase 3: Add metadata to each chunk (40-50%)
            self._progress(on_progress, "Adding metadata", 40)
            for i, chunk in enumerate(chunks):
                # Extract page number from source metadata
                page_num = chunk.metadata.get("page", 1) + 1  # 0-indexed to 1-indexed

                chunk.metadata.update({
                    "doc_id": doc_id,
                    "title": title,
                    "grade": grade,
                    "subject": subject,
                    "chunk_index": i,
                    "page_start": page_num,
                    "page_end": page_num,
                    "chunk_id": generate_id(),
                })
            self._progress(on_progress, "Metadata added", 50)

            # Phase 4: Store in Qdrant with batching (50-95%)
            self._progress(on_progress, "Storing in vector database", 50)

            # Batch processing for efficient embedding generation
            BATCH_SIZE = 50
            total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

            try:
                import aioitertools

                batch_idx = 0
                async for batch in aioitertools.batched(chunks, BATCH_SIZE):
                    batch_list = list(batch)
                    texts = [c.page_content for c in batch_list]
                    metadata_list = [c.metadata for c in batch_list]

                    await self.store.add(
                        texts=texts,
                        embeddings=[],
                        metadata=metadata_list,
                    )

                    batch_idx += 1
                    progress = 50 + int(45 * batch_idx / total_batches)
                    self._progress(on_progress, f"Batch {batch_idx}/{total_batches}", progress)

            except ImportError:
                # Fallback to sequential if aioitertools not installed
                texts = [c.page_content for c in chunks]
                metadata_list = [c.metadata for c in chunks]
                await self.store.add(
                    texts=texts,
                    embeddings=[],
                    metadata=metadata_list,
                )

            self._progress(on_progress, "Storage complete", 95)

            # Phase 5: Save chunks to PostgreSQL for citation FK (95-98%)
            from somaai.db.crud import create_chunks
            from somaai.db.session import async_session_maker

            chunk_records = [
                {
                    "id": c.metadata["chunk_id"],
                    "document_id": doc_id,
                    "content": c.page_content[:5000],  # Limit for DB storage
                    "page_start": c.metadata["page_start"],
                    "page_end": c.metadata["page_end"],
                    "chunk_index": c.metadata["chunk_index"],
                }
                for c in chunks
            ]

            async with async_session_maker() as db:
                await create_chunks(db, chunk_records)

            self._progress(on_progress, "Chunk metadata saved", 98)

            # Phase 6: Finalize (98-100%)
            self._progress(on_progress, "Finalizing", 98)
            result = {
                "status": "completed",
                "doc_id": doc_id,
                "chunks": len(chunks),
                "pages": len(pages),
                "title": title,
            }
            self._progress(on_progress, "Complete", 100)

            return result

        except Exception as e:
            self._progress(on_progress, f"Failed: {str(e)}", -1)
            raise

    def _progress(
        self,
        callback: Callable[[str, int], None] | None,
        stage: str,
        pct: int,
    ) -> None:
        """Report progress.

        Args:
            callback: Progress callback function
            stage: Current stage description
            pct: Percentage complete (0-100, or -1 for error)
        """
        if callback:
            callback(stage, pct)

    def _load_with_ocr(self, file_path: Path) -> list:
        """Load PDF using OCR (Optical Character Recognition).
        
        Requires: pdf2image, pytesseract, tesseract-ocr, poppler-utils
        """
        from pdf2image import convert_from_path
        import pytesseract
        from langchain_core.documents import Document
        
        # Convert PDF to images
        # thread_count matches CPU cores usually
        images = convert_from_path(str(file_path), thread_count=4)
        
        docs = []
        for i, image in enumerate(images):
            # Extract text from image
            text = pytesseract.image_to_string(image)
            docs.append(Document(page_content=text, metadata={"source": str(file_path), "page": i}))
            
        return docs
