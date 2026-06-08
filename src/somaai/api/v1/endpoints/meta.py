"""Meta endpoints for curriculum metadata."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.meta import (
    MetadataCreate,
    MetadataResponse,
    MetadataUpdate,
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


# ---------------------------------------------------------------------------
# Curriculum Metadata (grades + subjects)
# ---------------------------------------------------------------------------


@router.get("/metadata", response_model=list[MetadataResponse])
async def list_metadata(
    type: str | None = Query(None, description="Filter by type: 'grade' or 'subject'"),
    only_with_docs: bool = Query(
        False, description="If True, only return entries with documents"
    ),
    service: MetaService = Depends(_get_meta_service),
):
    """List curriculum metadata entries.

    Returns grades and/or subjects with display names and sort order.
    Use ?type=grade or ?type=subject to filter.
    """
    return await service.get_metadata(meta_type=type, only_with_docs=only_with_docs)


@router.post(
    "/metadata", response_model=MetadataResponse, status_code=status.HTTP_201_CREATED
)
async def create_metadata(
    data: MetadataCreate,
    service: MetaService = Depends(_get_meta_service),
):
    """Create a new curriculum metadata entry (grade or subject)."""
    from somaai.exceptions import (
        ConflictError,
        ValidationError,
        conflict_exception,
        validation_exception,
    )

    try:
        return await service.create_metadata(data)
    except ConflictError as e:
        raise conflict_exception(detail=str(e))
    except ValidationError as e:
        raise validation_exception(detail=str(e))


@router.patch("/metadata/{metadata_id}", response_model=MetadataResponse)
async def update_metadata(
    metadata_id: str,
    data: MetadataUpdate,
    service: MetaService = Depends(_get_meta_service),
):
    """Update an existing metadata entry."""
    entry = await service.update_metadata(metadata_id, data)
    if not entry:
        raise HTTPException(status_code=404, detail="Metadata entry not found")
    return entry


@router.delete("/metadata/{metadata_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_metadata(
    metadata_id: str,
    service: MetaService = Depends(_get_meta_service),
):
    """Delete a metadata entry."""
    success = await service.delete_metadata(metadata_id)
    if not success:
        raise HTTPException(status_code=404, detail="Metadata entry not found")


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


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


@router.post(
    "/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED
)
async def create_topic(
    topic_in: TopicCreate,
    service: MetaService = Depends(_get_meta_service),
):
    """Create a new topic."""
    from somaai.exceptions import (
        ConflictError,
        ValidationError,
        conflict_exception,
        validation_exception,
    )

    try:
        return await service.create_topic(topic_in)
    except ConflictError as e:
        raise conflict_exception(detail=str(e))
    except ValidationError as e:
        raise validation_exception(detail=str(e))


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
