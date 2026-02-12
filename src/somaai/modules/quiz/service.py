"""Quiz service for quiz management."""

from somaai.contracts.quiz import (
    QuizDownloadParams,
    QuizGenerateRequest,
    QuizResponse,
)


class QuizService:
    """Service for quiz operations.

    Handles quiz creation, retrieval, and download.
    Quiz generation logic is in QuizGenerator.
    """

    async def create_quiz(
        self,
        teacher_id: str,
        request: QuizGenerateRequest,
    ) -> tuple[str, str]:
        """Create a new quiz and enqueue generation.

        Args:
            teacher_id: Teacher user ID
            request: Quiz generation parameters

        Returns:
            Tuple of (quiz_id, job_id) for tracking

        Behavior:
            - Creates quiz record with 'pending' status
            - Enqueues background job for generation
        """
        pass

    async def get_quiz(self, quiz_id: str) -> QuizResponse | None:
        """Get quiz by ID.

        Args:
            quiz_id: Quiz identifier

        Returns:
            Quiz with items (if completed) or None if not found
        """
        pass

    async def list_quizzes(
        self,
        teacher_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List quizzes for a teacher.

        Args:
            teacher_id: Teacher user ID
            page: Page number
            page_size: Items per page

        Returns:
            Paginated list of quizzes
        """
        pass

    async def download_quiz(
        self,
        quiz_id: str,
        params: QuizDownloadParams,
    ) -> bytes:
        """Generate quiz download file.

        Args:
            quiz_id: Quiz identifier
            params: Download options (variant, format)

        Returns:
            File content as bytes (PDF or DOCX)

        Raises:
            ValueError: If quiz not found or not completed
        """
        pass

    async def delete_quiz(self, quiz_id: str) -> bool:
        """Delete a quiz.

        Args:
            quiz_id: Quiz identifier

        Returns:
            True if deleted, False if not found
        """
        pass
