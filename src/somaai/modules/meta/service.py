"""Meta service for curriculum metadata operations."""

from somaai.contracts.meta import GradeResponse, SubjectResponse, TopicResponse


class MetaService:
    """Service for curriculum metadata operations.

    Provides access to grades, subjects, and topics data
    from the Rwanda Education Board curriculum.
    """

    async def get_grades(self) -> list[GradeResponse]:
        """Get all available grade levels.

        Returns:
            List of grades (P1-P6, S1-S6) with display names

        Order:
            Returns grades in ascending order (P1, P2, ..., S6)
        """
        pass

    async def get_subjects(
        self,
        grade: str | None = None,
    ) -> list[SubjectResponse]:
        """Get subjects available for a grade.

        Args:
            grade: Grade ID to filter by (optional)

        Returns:
            List of subjects available for the grade
            Returns all subjects if grade is None
        """
        pass

    async def get_topics(
        self,
        grade: str,
        subject: str,
    ) -> list[TopicResponse]:
        """Get topics for a grade and subject combination.

        Args:
            grade: Grade ID (required)
            subject: Subject ID (required)

        Returns:
            List of topics as a tree structure (with children)

        Structure:
            Topics are hierarchical - main topics contain sub-topics
        """
        pass

    async def get_topic_by_id(self, topic_id: str) -> TopicResponse | None:
        """Get a single topic by ID.

        Args:
            topic_id: Topic ID

        Returns:
            Topic details or None if not found
        """
        pass

    async def get_topics_by_ids(
        self,
        topic_ids: list[str],
    ) -> list[TopicResponse]:
        """Get multiple topics by IDs.

        Args:
            topic_ids: List of topic IDs

        Returns:
            List of topics (in same order as input IDs)
        """
        pass
