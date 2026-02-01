"""Feedback service for response ratings."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.contracts.common import UserRole
from somaai.contracts.feedback import FeedbackRequest, FeedbackResponse
from somaai.db.models import Feedback, Message
from somaai.exceptions import ConflictError, NotFoundError
from somaai.utils.ids import generate_id
from somaai.utils.time import kigali_now


class FeedbackService:
    """Service for managing response feedback.

    Collects teacher feedback on AI-generated responses
    for quality improvement and analytics.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_feedback(
        self,
        request: FeedbackRequest,
        actor_id: str,
    ) -> FeedbackResponse:
        """Submit feedback for a message.

        Args:
            request: FeedbackRequest with message_id, useful, text, tags
            actor_id: Actor ID from request header (for tracking)

        Returns:
            Created feedback record

        Raises:
            NotFoundError: If message_id doesn't exist
            ConflictError: If feedback already exists for this message
        """
        message = await self.session.get(Message, request.message_id)
        if not message:
            raise NotFoundError(f"Message {request.message_id} not found")

        existing = await self._get_feedback_by_message(request.message_id)
        if existing:
            raise ConflictError(
                f"Feedback already exists for message {request.message_id}"
            )

        normalized_tags = self._normalize_tags(request.tags)

        feedback = Feedback(
            id=generate_id(),
            message_id=request.message_id,
            useful=request.useful,
            text=request.text,
            tags=normalized_tags,
            created_at=kigali_now(),
            updated_at=kigali_now(),
            actor_id=actor_id,
            user_role=request.user_role.value,
        )

        self.session.add(feedback)

        return self._to_response(feedback, request.user_role)

    async def _get_feedback_by_message(
        self,
        message_id: str,
    ) -> Feedback | None:
        """Get feedback for a specific message.

        Args:
            message_id: Message ID

        Returns:
            Feedback record or None if not submitted
        """
        stmt = select(Feedback).where(Feedback.message_id == message_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_feedback_for_message(
        self,
        message_id: str,
    ) -> FeedbackResponse | None:
        """Get feedback for a specific message.

        Args:
            message_id: Message ID

        Returns:
            Feedback record or None if not submitted
        """
        feedback = await self._get_feedback_by_message(message_id)
        if not feedback:
            return None

        raw_role = feedback.user_role
        if raw_role is None:
            return None
        try:
            user_role = UserRole(str(raw_role))
        except ValueError:
            return None
        return self._to_response(feedback, user_role)

    @staticmethod
    def _to_response(feedback: Feedback, user_role: UserRole) -> FeedbackResponse:
        """Convert Feedback model to FeedbackResponse.

        Args:
            feedback: Feedback model instance
            user_role: User role enum

        Returns:
            FeedbackResponse schema
        """
        return FeedbackResponse(
            feedback_id=cast(str, feedback.id),
            message_id=cast(str, feedback.message_id),
            useful=cast(bool, feedback.useful),
            text=cast(str | None, feedback.text),
            tags=cast(list[str] | None, feedback.tags),
            created_at=feedback.created_at,  # type: ignore[arg-type]
            user_role=user_role,
        )

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str] | None:
        """Normalize tags: lowercase, strip, dedupe, cap at 10.

        Args:
            tags: Raw tags from request

        Returns:
            Normalized tags or None
        """
        if not tags:
            return None
        cleaned = [t.strip().lower() for t in tags if t and t.strip()]
        deduplicated = list(dict.fromkeys(cleaned))
        return deduplicated[:10] if deduplicated else None

    async def get_feedback_stats(
        self,
        days: int = 30,
    ) -> dict:
        """Get aggregate feedback statistics.

        Args:
            days: Number of days to include

        Returns:
            Stats dict with:
            - total_feedback: count
            - useful_pct: percentage marked useful
            - common_tags: most common feedback tags
        """
        # TODO: Implement when needed for analytics
        return {
            "total_feedback": 0,
            "useful_pct": 0.0,
            "common_tags": [],
        }
