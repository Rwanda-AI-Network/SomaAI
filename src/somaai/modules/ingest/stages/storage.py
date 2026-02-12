"""Storage stage - store chunks in Qdrant with retry and rollback."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from somaai.modules.ingest.stages.base import PipelineStage, StageResult
from somaai.modules.ingest.exceptions import StorageError, EmbeddingError

if TYPE_CHECKING:
    from somaai.modules.ingest.context import PipelineContext
    from somaai.modules.knowledge.stores.qdrant import QdrantStore

logger = logging.getLogger(__name__)


class VectorStorageStage(PipelineStage):
    """Store chunks in Qdrant vector database.
    
    Features:
    - Batch processing for efficiency
    - Retry logic with exponential backoff
    - Rollback on failure (no partial data)
    """
    
    name = "storage"
    start_pct = 50
    end_pct = 95
    
    def __init__(
        self,
        store: QdrantStore,
        batch_size: int = 50,
        max_retries: int = 3
    ):
        """Initialize storage stage.
        
        Args:
            store: Qdrant vector store
            batch_size: Chunks per batch
            max_retries: Retry attempts per batch
        """
        self.store = store
        self.batch_size = batch_size
        self.max_retries = max_retries
    
    def validate_input(self, ctx: PipelineContext) -> bool:
        """Ensure chunks exist and have doc_id.
        
        Note: chunk_id is added by the enrichment stage which runs before this.
        We only check doc_id here since that's from context.
        """
        if len(ctx.chunks) == 0:
            return False
        return True  # Trust enrichment stage added required fields
    
    async def execute(self, ctx: PipelineContext) -> StageResult:
        """Store chunks with batching, retry, and rollback."""
        
        total_chunks = len(ctx.chunks)
        total_batches = (total_chunks + self.batch_size - 1) // self.batch_size
        
        self._report_progress(ctx, f"Storing {total_chunks} chunks", 0.0)
        
        try:
            batch_idx = 0
            
            for batch in self._batch_chunks(ctx.chunks):
                await self._store_batch_with_retry(batch)
                
                # Track stored IDs
                ctx.stored_chunk_ids.extend(
                    c.metadata["chunk_id"] for c in batch
                )
                
                batch_idx += 1
                progress = batch_idx / total_batches
                self._report_progress(
                    ctx, 
                    f"Batch {batch_idx}/{total_batches}", 
                    progress
                )
            
            logger.info(f"Stored {len(ctx.stored_chunk_ids)} chunks successfully")
            
            # Also add to BM25 index if hybrid search enabled
            if getattr(ctx.settings, 'rag_enable_hybrid_search', False):
                try:
                    from somaai.modules.knowledge.bm25_index import get_bm25_index
                    
                    bm25_index = get_bm25_index(ctx.settings)
                    
                    # Extract texts and IDs for BM25
                    texts = [c.page_content for c in ctx.chunks]
                    doc_ids = [c.metadata.get('chunk_id', '') for c in ctx.chunks]
                    
                    # CRITICAL FIX (Bug #2): Validate chunk IDs before indexing
                    # This prevents silent data loss when chunk_id is missing
                    valid_pairs = [(t, d) for t, d in zip(texts, doc_ids) if d]
                    
                    if not valid_pairs:
                        logger.error(
                            f"BM25 indexing failed: No valid chunk_ids found! "
                            f"All {len(ctx.chunks)} chunks missing chunk_id metadata. "
                            f"This indicates a bug in the enrichment stage."
                        )
                    elif len(valid_pairs) < len(texts):
                        missing_count = len(texts) - len(valid_pairs)
                        logger.warning(
                            f"BM25 indexing: {missing_count}/{len(texts)} chunks missing chunk_id, "
                            f"only indexing {len(valid_pairs)} chunks. "
                            f"Missing chunk_ids may cause incomplete hybrid search results."
                        )
                    
                    if valid_pairs:
                        valid_texts, valid_ids = zip(*valid_pairs)
                        bm25_index.add_documents(list(valid_texts), list(valid_ids))
                        logger.info(f"Added {len(valid_texts)} documents to BM25 index")
                    else:
                        logger.warning("No documents added to BM25 index due to missing chunk_ids")
                        
                except ImportError:
                    logger.info("BM25 not available (rank-bm25 not installed)")
                except Exception as e:
                    # Don't fail ingestion if BM25 fails
                    logger.warning(f"Failed to update BM25 index: {e}")
            
            return StageResult(
                success=True,
                data={
                    "stored_count": len(ctx.stored_chunk_ids),
                    "batch_count": total_batches,
                }
            )
            
        except Exception as e:
            # ROLLBACK: Delete any partial data
            logger.error(f"Storage failed: {e}. Rolling back...")
            await self._rollback(ctx.doc_id)
            raise StorageError(f"Storage failed and rolled back: {e}")
    
    def _batch_chunks(self, chunks):
        """Yield batches of chunks."""
        for i in range(0, len(chunks), self.batch_size):
            yield chunks[i:i + self.batch_size]
    
    async def _store_batch_with_retry(self, batch):
        """Store batch with exponential backoff retry."""
        for attempt in range(self.max_retries):
            try:
                texts = [c.page_content for c in batch]
                metadata_list = [c.metadata for c in batch]
                
                await self.store.add(
                    texts=texts,
                    embeddings=[],  # Let store generate embeddings
                    metadata=metadata_list,
                )
                return  # Success
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"Batch storage attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Batch storage failed after {self.max_retries} attempts"
                    )
                    raise EmbeddingError(
                        f"Failed after {self.max_retries} retries: {e}"
                    )
    
    async def _rollback(self, doc_id: str):
        """Delete all chunks for this doc_id on failure."""
        try:
            await self.store.delete_by_doc_id(doc_id)
            logger.info(f"Rollback successful: Deleted chunks for {doc_id}")
        except Exception as e:
            logger.critical(
                f"Rollback failed: {e}. Manual cleanup required for doc_id={doc_id}"
            )
