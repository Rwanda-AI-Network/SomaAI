"""RAG pipeline debug logging.

Provides structured, stage-by-stage logging for the RAG pipeline.
Enabled when settings.debug = True.

Usage in pipeline:
    debug = PipelineDebugger(enabled=settings.debug)
    debug.start(query, grade, subject)
    debug.log_stage("retrieve", docs_found=5, top_score=0.82)
    debug.end(response)

Output format:
    ============================================================
    RAG PIPELINE DEBUG
      Query: what are scheduling queues?
      Grade: S6
    ============================================================
    Stage: retrieve (342ms)
      docs_found: 5
      top_score: 0.82
    ============================================================
    PIPELINE COMPLETE (2166ms)
    ============================================================
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("somaai.rag.debug")


class PipelineDebugger:
    """Structured debug logging for RAG pipeline stages.

    Accumulates stage data (timing, doc counts, decisions) across
    a single pipeline run and logs them in a readable format.

    Controlled by settings.debug — does nothing when disabled.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.stages: list[dict] = []
        self.start_time: float = 0.0

    def start(self, query: str, grade: str, subject: str) -> None:
        """Start a new pipeline debug session."""
        if not self.enabled:
            return
        self.start_time = time.time()
        self.stages = []
        logger.info("=" * 60)
        logger.info("RAG PIPELINE DEBUG")
        logger.info("  Query: %s", query)
        logger.info("  Grade: %s | Subject: %s", grade, subject)
        logger.info("=" * 60)

    def log_stage(self, name: str, **kwargs) -> None:
        """Log a pipeline stage with arbitrary key-value data.

        Args:
            name: Stage name (e.g. "retrieve", "generate", "classify")
            **kwargs: Stage-specific data to log
        """
        if not self.enabled:
            return
        elapsed = (time.time() - self.start_time) * 1000
        stage = {"name": name, "elapsed_ms": round(elapsed), **kwargs}
        self.stages.append(stage)

        logger.info("")
        logger.info("Stage: %s (%dms)", name, elapsed)
        for key, value in kwargs.items():
            if isinstance(value, list):
                logger.info("  %s: %d items", key, len(value))
                # Show preview of first 3 items
                for i, item in enumerate(value[:3]):
                    if isinstance(item, dict):
                        preview = str(item.get("content", ""))[:80]
                        score = item.get("score", "?")
                        logger.info("    [%d] score=%s | %s...", i, score, preview)
                    else:
                        logger.info("    [%d] %s...", i, str(item)[:80])
            elif isinstance(value, str) and len(value) > 100:
                logger.info("  %s: %s...", key, value[:100])
            else:
                logger.info("  %s: %s", key, value)

    def end(self, response: dict) -> None:
        """End the pipeline debug session and log summary."""
        if not self.enabled:
            return
        total_ms = (time.time() - self.start_time) * 1000
        logger.info("")
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE (%dms)", total_ms)
        logger.info("  Sufficiency: %s", response.get("sufficiency"))
        logger.info("  Citations: %d", len(response.get("citations", [])))
        answer_preview = response.get("answer", "")[:120]
        logger.info("  Answer preview: %s...", answer_preview)
        stage_names = " → ".join(s["name"] for s in self.stages)
        logger.info("  Stages: %s", stage_names)
        logger.info("=" * 60)
