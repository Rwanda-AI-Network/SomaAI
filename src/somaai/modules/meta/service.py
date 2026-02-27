"""Metadata service with in-process TTL cache.

Serves curriculum metadata (grades, subjects, topics) from PostgreSQL
with a lightweight cache layer. Data is small (~53 KB max) and rarely
changes, so in-process caching avoids Redis overhead.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.meta import (
    GradeResponse,
    SubjectResponse,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from somaai.db import crud

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process TTL cache
# ---------------------------------------------------------------------------
# Metadata changes only via seed script or admin operations.
# 5-minute TTL is safe: worst case a new seed takes 5 min to surface.
_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 300  # seconds


######### COMENT: THIS IS ONLY FOR A SHORT TERM SOLUTION OR WE CAN ADD MORE SUBJECTS - THIS IS JUST TO MAKE THE UI CLEAN##########
GRADE_DISPLAY: dict[str, dict[str, str | int]] = {
    "P6": {"name": "Primary 6", "level": "primary", "order": 1},
    "S1": {"name": "Senior 1", "level": "secondary", "order": 2},
    "S2": {"name": "Senior 2", "level": "secondary", "order": 3},
    "S3": {"name": "Senior 3", "level": "secondary", "order": 4},
    "S4": {"name": "Senior 4", "level": "secondary", "order": 5},
    "S5": {"name": "Senior 5", "level": "secondary", "order": 6},
    "S6": {"name": "Senior 6", "level": "secondary", "order": 7},
}

SUBJECT_DISPLAY: dict[str, dict[str, str | int]] = {
    "computer_science": {"name": "Computer Science", "icon": "monitor", "order": 1},
    "mathematics": {"name": "Mathematics", "icon": "calculator", "order": 2},
    "biology": {"name": "Biology", "icon": "flask-conical", "order": 3},
    "physics": {"name": "Physics", "icon": "atom", "order": 4},
    "chemistry": {"name": "Chemistry", "icon": "beaker", "order": 5},
    "english": {"name": "English", "icon": "book", "order": 6},
    "accounting": {"name": "Accounting", "icon": "file-spreadsheet", "order": 7},
}


def _get_cached(key: str) -> Any | None:
    """Return cached value if not expired, else None."""
    entry = _cache.get(key)
    if entry is not None:
        expires, value = entry
        if time.monotonic() < expires:
            return value
        del _cache[key]
    return None


def _set_cached(key: str, value: Any) -> None:
    """Store value with TTL."""
    _cache[key] = (time.monotonic() + CACHE_TTL, value)


def invalidate_meta_cache() -> None:
    """Clear all cached metadata. Call after seeding or admin changes."""
    _cache.clear()
    logger.info("Meta cache invalidated")


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

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # async def get_grades(self) -> list[GradeResponse]:
    #     """Get all available grade levels.

    #     Returns:
    #         List of grades (P6, S1-S6) sorted by display_order
    #     """
    #     cached = _get_cached("grades")
    #     if cached is not None:
    #         return cached

    #     grades = await crud.get_all_grades(self.db)
    #     result = [
    #         GradeResponse(
    #             id=g.id,
    #             name=g.name,
    #             display_order=g.display_order,
    #             level=g.level,
    #         )
    #         for g in grades
    #     ]
    #     _set_cached("grades", result)
    #     logger.debug("Cached %d grades", len(result))
    #     return result

    async def get_grades(self) -> list[GradeResponse]:
        """Get grade levels derived from ingested documents.

        Only returns grades that have at least one document in the DB.
        """
        cached = _get_cached("grades")
        if cached is not None:
            return cached

        grade_ids = await crud.get_distinct_grades(self.db)  # e.g. ["S2", "S6"]
        result = [
            GradeResponse(
                id=gid,
                name=GRADE_DISPLAY.get(gid, {}).get("name", gid),
                display_order=GRADE_DISPLAY.get(gid, {}).get("order", 99),
                level=GRADE_DISPLAY.get(gid, {}).get("level", "unknown"),
            )
            for gid in grade_ids
        ]
        # Sort by display_order so UI shows them in logical order
        result.sort(key=lambda g: g.display_order)
        _set_cached("grades", result)
        logger.debug("Cached %d grades (from documents)", len(result))
        return result


    # async def get_subjects(
    #     self,
    #     grade: str | None = None,
    # ) -> list[SubjectResponse]:
    #     """Get subjects, optionally filtered by grade document availability.

    #     Args:
    #         grade: Grade ID to filter by (e.g., 'S2'). If None, returns all.

    #     Returns:
    #         List of subjects sorted by display_order
    #     """
    #     cache_key = f"subjects:{grade or 'all'}"
    #     cached = _get_cached(cache_key)
    #     if cached is not None:
    #         return cached

    #     if grade:
    #         subjects = await crud.get_subjects_for_grade(self.db, grade)
    #     else:
    #         subjects = await crud.get_all_subjects(self.db)

    #     result = [
    #         SubjectResponse(
    #             id=s.id,
    #             name=s.name,
    #             display_order=s.display_order,
    #             icon=s.icon,
    #         )
    #         for s in subjects
    #     ]
    #     _set_cached(cache_key, result)
    #     logger.debug("Cached %d subjects for %s", len(result), grade or "all")
    #     return result

    async def get_subjects(
        self,
        grade: str | None = None,
    ) -> list[SubjectResponse]:
        """Get subjects derived from ingested documents.

        Only returns subjects that have at least one document.
        If grade is specified, only subjects with documents for that grade.
        """
        cache_key = f"subjects:{grade or 'all'}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        subject_ids = await crud.get_distinct_subjects(self.db, grade)
        # e.g. ["biology", "computer_science"]

        result = [
            SubjectResponse(
                id=sid,
                name=SUBJECT_DISPLAY.get(sid, {}).get("name", sid.replace("_", " ").title()),
                display_order=SUBJECT_DISPLAY.get(sid, {}).get("order", 99),
                icon=SUBJECT_DISPLAY.get(sid, {}).get("icon"),
            )
            for sid in subject_ids
        ]
        result.sort(key=lambda s: s.display_order)
        _set_cached(cache_key, result)
        logger.debug("Cached %d subjects for %s (from documents)", len(result), grade or "all")
        return result

        #######################################END############


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
        cached = _get_cached(cache_key)
        if cached is not None:
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
        _set_cached(cache_key, result)
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

    # async def create_grade(self, grade_in: GradeCreate) -> GradeResponse:
    #     """Create a new grade and invalidate cache."""
    #     grade = await crud.create_grade(self.db, grade_in.model_dump())
    #     invalidate_meta_cache()
    #     return GradeResponse(
    #         id=grade.id,
    #         name=grade.name,
    #         display_order=grade.display_order,
    #         level=grade.level,
    #     )

    # async def update_grade(
    #     self, grade_id: str, grade_in: GradeUpdate
    # ) -> GradeResponse | None:
    #     """Update a grade and invalidate cache."""
    #     grade = await crud.update_grade(
    #         self.db, grade_id, grade_in.model_dump(exclude_unset=True)
    #     )
    #     if not grade:
    #         return None
    #     invalidate_meta_cache()
    #     return GradeResponse(
    #         id=grade.id,
    #         name=grade.name,
    #         display_order=grade.display_order,
    #         level=grade.level,
    #     )

    # async def delete_grade(self, grade_id: str) -> bool:
    #     """Delete a grade and invalidate cache."""
    #     success = await crud.delete_grade(self.db, grade_id)
    #     if success:
    #         invalidate_meta_cache()
    #     return success

    # async def create_subject(self, subject_in: SubjectCreate) -> SubjectResponse:
    #     """Create a new subject and invalidate cache."""
    #     subject = await crud.create_subject(self.db, subject_in.model_dump())
    #     invalidate_meta_cache()
    #     return SubjectResponse(
    #         id=subject.id,
    #         name=subject.name,
    #         display_order=subject.display_order,
    #         icon=subject.icon,
    #     )

    # async def update_subject(
    #     self, subject_id: str, subject_in: SubjectUpdate
    # ) -> SubjectResponse | None:
    #     """Update a subject and invalidate cache."""
    #     subject = await crud.update_subject(
    #         self.db, subject_id, subject_in.model_dump(exclude_unset=True)
    #     )
    #     if not subject:
    #         return None
    #     invalidate_meta_cache()
    #     return SubjectResponse(
    #         id=subject.id,
    #         name=subject.name,
    #         display_order=subject.display_order,
    #         icon=subject.icon,
    #     )

    # async def delete_subject(self, subject_id: str) -> bool:
    #     """Delete a subject and invalidate cache."""
    #     success = await crud.delete_subject(self.db, subject_id)
    #     if success:
    #         invalidate_meta_cache()
    #     return success

    # async def create_topic(self, topic_in: TopicCreate) -> TopicResponse:
    #     """Create a new topic and invalidate cache."""
    #     import uuid

    #     topic_id = str(uuid.uuid4())
    #     topic = await crud.create_topic(self.db, topic_id, topic_in.model_dump())
    #     invalidate_meta_cache()
    #     return TopicResponse(
    #         topic_id=topic.id,
    #         title=topic.title,
    #         grade=topic.grade,
    #         subject=topic.subject,
    #         doc_id=topic.doc_id or "",
    #         page_start=topic.page_start,
    #         page_end=topic.page_end,
    #         path=topic.path or [],
    #         document_count=1 if topic.doc_id else 0,
    #     )

    async def update_topic(
        self, topic_id: str, topic_in: TopicUpdate
    ) -> TopicResponse | None:
        """Update a topic and invalidate cache."""
        topic = await crud.update_topic(
            self.db, topic_id, topic_in.model_dump(exclude_unset=True)
        )
        if not topic:
            return None
        invalidate_meta_cache()
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
            invalidate_meta_cache()
        return success
