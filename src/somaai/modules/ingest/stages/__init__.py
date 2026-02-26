"""Ingest pipeline stages.

Each stage is a focused component responsible for one step
of the ingestion process.
"""

from somaai.modules.ingest.stages.base import PipelineStage, StageResult
from somaai.modules.ingest.stages.chunking import ChunkingStage
from somaai.modules.ingest.stages.db_sync import DatabaseSyncStage
from somaai.modules.ingest.stages.deduplication import DeduplicationStage
from somaai.modules.ingest.stages.enrichment import MetadataEnrichmentStage
from somaai.modules.ingest.stages.extraction import ExtractionStage
from somaai.modules.ingest.stages.filtering import QualityFilterStage
from somaai.modules.ingest.stages.storage import VectorStorageStage

__all__ = [
    "PipelineStage",
    "StageResult",
    "DeduplicationStage",
    "ExtractionStage",
    "ChunkingStage",
    "QualityFilterStage",
    "MetadataEnrichmentStage",
    "VectorStorageStage",
    "DatabaseSyncStage",
]
