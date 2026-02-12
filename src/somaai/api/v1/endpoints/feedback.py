"""Feedback endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.feedback import FeedbackRequest, FeedbackResponse
from somaai.db.session import get_session
from somaai.deps import get_actor_id
from somaai.exceptions import (
    ConflictError,
    NotFoundError,
    conflict_exception,
    not_found_exception,
)
from somaai.modules.feedback.service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_session),
    actor_id: str = Depends(get_actor_id),
) -> FeedbackResponse:
    """Submit feedback for an AI response.

    Request body:
    - message_id: Required - ID of message being rated
    - useful: Required - boolean rating
    - text: Optional - detailed feedback text
    - tags: Optional - list of feedback categories

    Returns:
    - 201 with feedback_id on success
    - 404 if message_id not found
    - 409 if feedback already exists

    Used by teachers to rate response quality.
    """
    service = FeedbackService(db)

    try:
        return await service.submit_feedback(data, actor_id)
    except NotFoundError as e:
        raise not_found_exception(str(e))
    except ConflictError as e:
        raise conflict_exception(str(e))


@router.get("/{message_id}", response_model=FeedbackResponse)
async def get_feedback(
    message_id: str,
    db: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """Get feedback for a specific message.

    Path parameters:
    - message_id: ID of the message

    Returns:
    - 200 with feedback details if found
    - 404 if no feedback exists

    Used to check if user already submitted feedback.
    """
    service = FeedbackService(db)
    feedback = await service.get_feedback_for_message(message_id)

    if not feedback:
        raise not_found_exception(f"Feedback for message {message_id} not found")
    return feedback
