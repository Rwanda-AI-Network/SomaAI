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
    GradeCreate,
    GradeResponse,
    GradeUpdate,
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
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
        grades = await service.get_grades()
    """

    async def check_exists_grade(self, grade_id: str) -> bool:
        """Check if a grade exists (uses L1 cache)."""
        from somaai.utils.meta import normalize_grade

        grade_id = normalize_grade(grade_id)
        grades = await self.get_grades()
        return any(g.id == grade_id for g in grades)

    async def check_exists_subject(self, subject_id: str) -> bool:
        """Check if a subject exists (uses L1 cache)."""
        from somaai.utils.meta import normalize_subject

        subject_id = normalize_subject(subject_id)
        subjects = await self.get_subjects()
        return any(s.id == subject_id for s in subjects)

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_grades(self, only_with_docs: bool = False) -> list[GradeResponse]:
        """Get all available grade levels.

        Args:
            only_with_docs: If True, only return grades that have at least one document.

        Returns:
            List of grades sorted by display_order
        """
        cache_key = f"grades:only_docs={only_with_docs}"
        cached = await _get_cached(cache_key)
        if cached is not None:
            # Deserialize from cache (dicts → Pydantic models)
            if cached and isinstance(cached[0], dict):
                return [GradeResponse(**g) for g in cached]
            return cached

        if only_with_docs:
            grade_ids = await crud.get_distinct_grades(self.db)
            # Find the actual Grade objects for these IDs to get full metadata
            all_grades = await crud.get_all_grades(self.db)
            grades = [g for g in all_grades if g.id in grade_ids]
        else:
            grades = await crud.get_all_grades(self.db)

        result = [
            GradeResponse(
                id=g.id,
                name=g.name,
                display_order=g.display_order,
                level=g.level,
            )
            for g in grades
        ]
        # Sort by display_order
        result.sort(key=lambda g: g.display_order)
        await _set_cached(cache_key, result)
        logger.debug("Cached %d grades (only_docs=%s)", len(result), only_with_docs)
        return result

    async def get_subjects(
        self,
        grade: str | None = None,
        only_with_docs: bool = False,
    ) -> list[SubjectResponse]:
        """Get subjects, optionally filtered by grade and document availability.

        Args:
            grade: Grade ID to filter by.
            only_with_docs: If True, only return subjects that have documents.

        Returns:
            List of subjects sorted by display_order
        """
        cache_key = f"subjects:grade={grade}:only_docs={only_with_docs}"
        cached = await _get_cached(cache_key)
        if cached is not None:
            # Deserialize from cache (dicts → Pydantic models)
            if cached and isinstance(cached[0], dict):
                return [SubjectResponse(**s) for s in cached]
            return cached

        if only_with_docs:
            subject_ids = await crud.get_distinct_subjects(self.db, grade)
            all_subjects = await crud.get_all_subjects(self.db)
            subjects = [s for s in all_subjects if s.id in subject_ids]
        else:
            subjects = await crud.get_all_subjects(self.db)

        result = [
            SubjectResponse(
                id=s.id,
                name=s.name,
                display_order=s.display_order,
                icon=s.icon,
            )
            for s in subjects
        ]
        result.sort(key=lambda s: s.display_order)
        await _set_cached(cache_key, result)
        logger.debug(
            "Cached %d subjects (grade=%s, only_docs=%s)",
            len(result),
            grade,
            only_with_docs,
        )
        return result

    async def get_topics(
        self,
        grade: str,
        subject: str,
    ) -> list[TopicResponse]:
        """Get topics for a grade and subject combination.

        Args:
            grade: Grade ID (required, e.g., 'S2')
            subject: Subject ID (required, e.g., 'biology')

        Returns:
            List of topics sorted by page_start
        """
        cache_key = f"topics:{grade}:{subject}"
        cached = await _get_cached(cache_key)
        if cached is not None:
            # Deserialize from cache (dicts → Pydantic models)
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
        """Get a single topic by ID.

        Args:
            topic_id: Topic ID

        Returns:
            Topic details or None if not found
        """
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
        """Get multiple topics by IDs.

        Args:
            topic_ids: List of topic IDs

        Returns:
            List of topics (order may differ from input)
        """
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
    # Mutations
    # ---------------------------------------------------------------------------

    async def _invalidate_all_cache(self) -> None:
        """Clear both L1 (in-process) and L2 (Redis) caches."""
        invalidate_meta_cache()  # L1 — sync
        await _invalidate_l2()  # L2 — async, best-effort

    async def create_grade(self, grade_in: GradeCreate) -> GradeResponse:
        """Create a new grade and invalidate cache.

        Raises:
            ConflictError: If grade with same ID already exists
        """
        from somaai.utils.meta import normalize_grade

        # Enforce canonical normalization on write
        grade_dict = grade_in.model_dump()
        grade_dict["id"] = normalize_grade(grade_dict["id"])

        grade = await crud.create_grade(self.db, grade_dict)
        await self._invalidate_all_cache()
        return GradeResponse(
            id=grade.id,
            name=grade.name,
            display_order=grade.display_order,
            level=grade.level,
        )

    async def update_grade(
        self, grade_id: str, grade_in: GradeUpdate
    ) -> GradeResponse | None:
        """Update a grade and invalidate cache."""
        grade = await crud.update_grade(
            self.db, grade_id, grade_in.model_dump(exclude_unset=True)
        )
        if not grade:
            return None
        await self._invalidate_all_cache()
        return GradeResponse(
            id=grade.id,
            name=grade.name,
            display_order=grade.display_order,
            level=grade.level,
        )

    async def delete_grade(self, grade_id: str) -> bool:
        """Delete a grade and invalidate cache."""
        success = await crud.delete_grade(self.db, grade_id)
        if success:
            await self._invalidate_all_cache()
        return success

    async def create_subject(self, subject_in: SubjectCreate) -> SubjectResponse:
        """Create a new subject and invalidate cache.

        Raises:
            ConflictError: If subject with same ID already exists
        """
        from somaai.utils.meta import normalize_subject

        # Enforce canonical normalization on write
        subject_dict = subject_in.model_dump()
        subject_dict["id"] = normalize_subject(subject_dict["id"])

        subject = await crud.create_subject(self.db, subject_dict)
        await self._invalidate_all_cache()
        return SubjectResponse(
            id=subject.id,
            name=subject.name,
            display_order=subject.display_order,
            icon=subject.icon,
        )

    async def update_subject(
        self, subject_id: str, subject_in: SubjectUpdate
    ) -> SubjectResponse | None:
        """Update a subject and invalidate cache."""
        subject = await crud.update_subject(
            self.db, subject_id, subject_in.model_dump(exclude_unset=True)
        )
        if not subject:
            return None
        await self._invalidate_all_cache()
        return SubjectResponse(
            id=subject.id,
            name=subject.name,
            display_order=subject.display_order,
            icon=subject.icon,
        )

    async def delete_subject(self, subject_id: str) -> bool:
        """Delete a subject and invalidate cache."""
        success = await crud.delete_subject(self.db, subject_id)
        if success:
            await self._invalidate_all_cache()
        return success

    async def create_topic(self, topic_in: TopicCreate) -> TopicResponse:
        """Create a new topic and invalidate cache.

        Raises:
            ConflictError: If topic with same ID already exists
        """
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
