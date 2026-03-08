"""Metadata service with two-tier (L1 + L2) TTL cache.

Serves curriculum metadata (grades, subjects, topics) from PostgreSQL
with a two-tier cache:
- **L1**: In-process dict (60s TTL) — sub-millisecond reads within a worker.
- **L2**: Redis db/2 (5min TTL) — cross-worker consistency.

Redis failures degrade gracefully to L1-only operation.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.meta import (
    MetadataCreate,
    MetadataResponse,
    MetadataUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from somaai.db import crud

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Two-tier TTL cache: L1 (in-process) + L2 (Redis)
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, Any]] = {}  # L1
CACHE_L1_TTL = 60  # 1 minute in-process
CACHE_L2_TTL = 300  # 5 minutes in Redis
CACHE_TTL = CACHE_L2_TTL  # Legacy alias for tests
_L2_PREFIX = "meta:"  # Redis key namespace


def _json_default(obj: Any) -> Any:
    """JSON serialiser fallback for Pydantic models."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def _get_cached(key: str) -> Any | None:
    """Two-tier lookup: L1 (in-process) → L2 (Redis)."""
    # L1 check
    entry = _cache.get(key)
    if entry is not None:
        expires, value = entry
        if time.monotonic() < expires:
            return value
        del _cache[key]

    # L2 check (Redis)
    try:
        from somaai.utils.redis import get_cache_redis

        redis = await get_cache_redis()
        raw = await redis.get(f"{_L2_PREFIX}{key}")
        if raw:
            value = json.loads(raw)
            # Promote to L1
            _cache[key] = (time.monotonic() + CACHE_L1_TTL, value)
            return value
    except Exception:  # noqa: BLE001 — Redis down is non-fatal
        pass

    return None


async def _set_cached(key: str, value: Any) -> None:
    """Write to L1 + L2."""
    _cache[key] = (time.monotonic() + CACHE_L1_TTL, value)
    try:
        from somaai.utils.redis import get_cache_redis

        redis = await get_cache_redis()
        await redis.setex(
            f"{_L2_PREFIX}{key}",
            CACHE_L2_TTL,
            json.dumps(value, default=_json_default),
        )
    except Exception:  # noqa: BLE001
        pass  # L1 still works


def invalidate_meta_cache() -> None:
    """Clear L1 cache (sync). L2 cleared async via _invalidate_l2()."""
    _cache.clear()
    logger.info("Meta L1 cache invalidated")


async def _invalidate_l2() -> None:
    """Clear all L2 (Redis) meta keys. Best-effort."""
    try:
        from somaai.utils.redis import get_cache_redis

        redis = await get_cache_redis()

        # Check if scan_iter is a mock (tests) or real Redis
        scan_iter = redis.scan_iter(match=f"{_L2_PREFIX}*")

        # If it's a mock, it won't have __aiter__, skip gracefully
        if not hasattr(scan_iter, "__aiter__"):
            return

        keys = [k async for k in scan_iter]
        if keys:
            await redis.delete(*keys)
            logger.info("Meta L2 cache invalidated (%d keys)", len(keys))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MetaService:
    """Service for curriculum metadata operations.

    Provides access to grades, subjects, and topics data
    from the Rwanda Education Board curriculum.

    Usage:
        service = MetaService(db_session)
        grades = await service.get_metadata(meta_type="grade")
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------------------
    # Metadata (grades + subjects)
    # ---------------------------------------------------------------------------

    async def get_metadata(
        self,
        meta_type: str | None = None,
        only_with_docs: bool = False,
    ) -> list[MetadataResponse]:
        """Get curriculum metadata entries.

        Args:
            meta_type: Filter by type ('grade' or 'subject'). None = all.
            only_with_docs: If True, only return entries that have documents.

        Returns:
            List of metadata entries sorted by display_order
        """
        cache_key = f"metadata:type={meta_type}:only_docs={only_with_docs}"
        cached = await _get_cached(cache_key)
        if cached is not None:
            if cached and isinstance(cached[0], dict):
                return [MetadataResponse(**m) for m in cached]
            return cached

        entries = await crud.get_all_metadata(self.db, meta_type)

        if only_with_docs:
            # Filter to only entries whose key appears in documents
            if meta_type == "grade":
                doc_keys = await crud.get_distinct_grades(self.db)
            elif meta_type == "subject":
                doc_keys = await crud.get_distinct_subjects(self.db)
            else:
                doc_keys = set()
            entries = [e for e in entries if e.key in doc_keys]

        result = [
            MetadataResponse(
                id=e.id,
                type=e.type,
                key=e.key,
                name=e.name,
                display_order=e.display_order,
                is_active=e.is_active,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
            for e in entries
        ]
        result.sort(key=lambda m: m.display_order)
        await _set_cached(cache_key, result)
        logger.debug(
            "Cached %d metadata (type=%s, only_docs=%s)",
            len(result),
            meta_type,
            only_with_docs,
        )
        return result

    async def check_exists_grade(self, grade_key: str) -> bool:
        """Check if a grade exists (uses cache)."""
        from somaai.utils.meta import normalize_grade

        grade_key = normalize_grade(grade_key)
        entries = await self.get_metadata(meta_type="grade")
        return any(e.key == grade_key for e in entries)

    async def check_exists_subject(self, subject_key: str) -> bool:
        """Check if a subject exists (uses cache)."""
        from somaai.utils.meta import normalize_subject

        subject_key = normalize_subject(subject_key)
        entries = await self.get_metadata(meta_type="subject")
        return any(e.key == subject_key for e in entries)

    async def create_metadata(self, data: MetadataCreate) -> MetadataResponse:
        """Create a new metadata entry and invalidate cache.

        Raises:
            ConflictError: If entry with same key already exists
        """
        import uuid

        entry_dict = data.model_dump()
        entry_dict["id"] = str(uuid.uuid4())

        # Normalize key based on type
        if data.type == "grade":
            entry_dict["key"] = entry_dict["key"].upper()
        elif data.type == "subject":
            entry_dict["key"] = entry_dict["key"].lower()

        entry = await crud.create_metadata(self.db, entry_dict)
        await self._invalidate_all_cache()
        return MetadataResponse(
            id=entry.id,
            type=entry.type,
            key=entry.key,
            name=entry.name,
            display_order=entry.display_order,
            is_active=entry.is_active,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    async def update_metadata(
        self, metadata_id: str, data: MetadataUpdate
    ) -> MetadataResponse | None:
        """Update a metadata entry and invalidate cache."""
        entry = await crud.update_metadata(
            self.db, metadata_id, data.model_dump(exclude_unset=True)
        )
        if not entry:
            return None
        await self._invalidate_all_cache()
        return MetadataResponse(
            id=entry.id,
            type=entry.type,
            key=entry.key,
            name=entry.name,
            display_order=entry.display_order,
            is_active=entry.is_active,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    async def delete_metadata(self, metadata_id: str) -> bool:
        """Delete a metadata entry and invalidate cache."""
        success = await crud.delete_metadata(self.db, metadata_id)
        if success:
            await self._invalidate_all_cache()
        return success

    # ---------------------------------------------------------------------------
    # Topics
    # ---------------------------------------------------------------------------

    async def get_topics(
        self,
        grade: str,
        subject: str,
    ) -> list[TopicResponse]:
        """Get topics for a grade and subject combination."""
        cache_key = f"topics:{grade}:{subject}"
        cached = await _get_cached(cache_key)
        if cached is not None:
            if cached and isinstance(cached[0], dict):
                return [TopicResponse(**t) for t in cached]
            return cached

        topics = await crud.get_topics_by_grade_subject(self.db, grade, subject)
        result = [
            TopicResponse(
                topic_id=t.id,
                title=t.title,
                grade=t.grade,
                subject=t.subject,
                doc_id=t.doc_id or "",
                page_start=t.page_start,
                page_end=t.page_end,
                path=t.path or [],
                document_count=1 if t.doc_id else 0,
            )
            for t in topics
        ]
        await _set_cached(cache_key, result)
        logger.debug("Cached %d topics for %s/%s", len(result), grade, subject)
        return result

    async def get_topic_by_id(self, topic_id: str) -> TopicResponse | None:
        """Get a single topic by ID."""
        topic = await crud.get_topic_by_id(self.db, topic_id)
        if topic is None:
            return None
        return TopicResponse(
            topic_id=topic.id,
            title=topic.title,
            grade=topic.grade,
            subject=topic.subject,
            doc_id=topic.doc_id or "",
            page_start=topic.page_start,
            page_end=topic.page_end,
            path=topic.path or [],
            document_count=1 if topic.doc_id else 0,
        )

    async def get_topics_by_ids(
        self,
        topic_ids: list[str],
    ) -> list[TopicResponse]:
        """Get multiple topics by IDs."""
        topics = await crud.get_topics_by_ids(self.db, topic_ids)
        return [
            TopicResponse(
                topic_id=t.id,
                title=t.title,
                grade=t.grade,
                subject=t.subject,
                doc_id=t.doc_id or "",
                page_start=t.page_start,
                page_end=t.page_end,
                path=t.path or [],
                document_count=1 if t.doc_id else 0,
            )
            for t in topics
        ]

    # ---------------------------------------------------------------------------
    # Topic mutations
    # ---------------------------------------------------------------------------

    async def create_topic(self, topic_in: TopicCreate) -> TopicResponse:
        """Create a new topic and invalidate cache."""
        import uuid

        topic_id = str(uuid.uuid4())
        topic = await crud.create_topic(self.db, topic_id, topic_in.model_dump())
        await self._invalidate_all_cache()
        return TopicResponse(
            topic_id=topic.id,
            title=topic.title,
            grade=topic.grade,
            subject=topic.subject,
            doc_id=topic.doc_id or "",
            page_start=topic.page_start,
            page_end=topic.page_end,
            path=topic.path or [],
            document_count=1 if topic.doc_id else 0,
        )

    async def update_topic(
        self, topic_id: str, topic_in: TopicUpdate
    ) -> TopicResponse | None:
        """Update a topic and invalidate cache."""
        topic = await crud.update_topic(
            self.db, topic_id, topic_in.model_dump(exclude_unset=True)
        )
        if not topic:
            return None
        await self._invalidate_all_cache()
        return TopicResponse(
            topic_id=topic.id,
            title=topic.title,
            grade=topic.grade,
            subject=topic.subject,
            doc_id=topic.doc_id or "",
            page_start=topic.page_start,
            page_end=topic.page_end,
            path=topic.path or [],
            document_count=1 if topic.doc_id else 0,
        )

    async def delete_topic(self, topic_id: str) -> bool:
        """Delete a topic and invalidate cache."""
        success = await crud.delete_topic(self.db, topic_id)
        if success:
            await self._invalidate_all_cache()
        return success

    # ---------------------------------------------------------------------------
    # Cache invalidation
    # ---------------------------------------------------------------------------

    async def _invalidate_all_cache(self) -> None:
        """Clear both L1 (in-process) and L2 (Redis) caches."""
        invalidate_meta_cache()  # L1 — sync
        await _invalidate_l2()  # L2 — async, best-effort
