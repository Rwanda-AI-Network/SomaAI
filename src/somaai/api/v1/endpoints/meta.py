"""Meta endpoints for curriculum metadata."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from somaai.db.session import get_session
from somaai.modules.meta.service import MetaService

router = APIRouter(prefix="/meta", tags=["meta"])


def _get_meta_service(db: AsyncSession = Depends(get_session)) -> MetaService:
    """Dependency factory for MetaService."""
    return MetaService(db)


@router.get("/grades", response_model=list[GradeResponse])
async def get_grades(
    only_with_docs: bool = Query(
        False, description="If True, only return grades with documents"
    ),
    service: MetaService = Depends(_get_meta_service),
):
    """Get all available grade levels.

    Returns list of grades (P6, S1-S6) with display names and sort order.
    """
    return await service.get_grades(only_with_docs=only_with_docs)


@router.get("/subjects", response_model=list[SubjectResponse])
async def get_subjects(
    grade: str | None = Query(None, description="Filter by grade ID"),
    only_with_docs: bool = Query(
        False, description="If True, only return subjects with documents"
    ),
    service: MetaService = Depends(_get_meta_service),
):
    """Get available subjects.

    Optionally filter by grade level. When filtered, returns only subjects
    that have ingested documents for that grade. Returns all subjects if
    no grade specified or no documents exist yet.
    """
    return await service.get_subjects(grade, only_with_docs=only_with_docs)


@router.get("/topics", response_model=list[TopicResponse])
async def get_topics(
    grade: str = Query(..., description="Grade ID (required)"),
    subject: str = Query(..., description="Subject ID (required)"),
    service: MetaService = Depends(_get_meta_service),
):
    """Get topics for a grade and subject.

    Returns topic list for curriculum navigation.
    Topics include document count for availability indication.
    """
    return await service.get_topics(grade, subject)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@router.post(
    "/grades", response_model=GradeResponse, status_code=status.HTTP_201_CREATED
)
async def create_grade(
    grade_in: GradeCreate,
    service: MetaService = Depends(_get_meta_service),
):
    """Create a new grade level."""
    return await service.create_grade(grade_in)


@router.patch("/grades/{grade_id}", response_model=GradeResponse)
async def update_grade(
    grade_id: str,
    grade_in: GradeUpdate,
    service: MetaService = Depends(_get_meta_service),
):
    """Update an existing grade level."""
    grade = await service.update_grade(grade_id, grade_in)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    return grade


@router.delete("/grades/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grade(
    grade_id: str,
    service: MetaService = Depends(_get_meta_service),
):
    """Delete a grade level."""
    success = await service.delete_grade(grade_id)
    if not success:
        raise HTTPException(status_code=404, detail="Grade not found")


@router.post(
    "/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED
)
async def create_subject(
    subject_in: SubjectCreate,
    service: MetaService = Depends(_get_meta_service),
):
    """Create a new subject."""
    return await service.create_subject(subject_in)


@router.patch("/subjects/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: str,
    subject_in: SubjectUpdate,
    service: MetaService = Depends(_get_meta_service),
):
    """Update an existing subject."""
    subject = await service.update_subject(subject_id, subject_in)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: str,
    service: MetaService = Depends(_get_meta_service),
):
    """Delete a subject."""
    success = await service.delete_subject(subject_id)
    if not success:
        raise HTTPException(status_code=404, detail="Subject not found")


@router.post(
    "/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED
)
async def create_topic(
    topic_in: TopicCreate,
    service: MetaService = Depends(_get_meta_service),
):
    """Create a new topic."""
    return await service.create_topic(topic_in)


@router.patch("/topics/{topic_id}", response_model=TopicResponse)
async def update_topic(
    topic_id: str,
    topic_in: TopicUpdate,
    service: MetaService = Depends(_get_meta_service),
):
    """Update an existing topic."""
    topic = await service.update_topic(topic_id, topic_in)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: str,
    service: MetaService = Depends(_get_meta_service),
):
    """Delete a topic."""
    success = await service.delete_topic(topic_id)
    if not success:
        raise HTTPException(status_code=404, detail="Topic not found")
