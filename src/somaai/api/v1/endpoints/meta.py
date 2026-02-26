"""Meta endpoints for curriculum metadata."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.meta import GradeResponse, SubjectResponse, TopicResponse
from somaai.db.session import get_session
from somaai.modules.meta.service import MetaService

router = APIRouter(prefix="/meta", tags=["meta"])


def _get_meta_service(db: AsyncSession = Depends(get_session)) -> MetaService:
    """Dependency factory for MetaService."""
    return MetaService(db)


@router.get("/grades", response_model=list[GradeResponse])
async def get_grades(
    service: MetaService = Depends(_get_meta_service),
):
    """Get all available grade levels.

    Returns list of grades (P6, S1-S6) with display names and sort order.
    """
    return await service.get_grades()


@router.get("/subjects", response_model=list[SubjectResponse])
async def get_subjects(
    grade: str | None = Query(None, description="Filter by grade ID"),
    service: MetaService = Depends(_get_meta_service),
):
    """Get available subjects.

    Optionally filter by grade level. When filtered, returns only subjects
    that have ingested documents for that grade. Returns all subjects if
    no grade specified or no documents exist yet.
    """
    return await service.get_subjects(grade)


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
