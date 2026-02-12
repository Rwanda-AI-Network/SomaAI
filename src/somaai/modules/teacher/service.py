"""Teacher profile service."""

from somaai.contracts.teacher import TeacherProfileRequest, TeacherProfileResponse


class TeacherService:
    """Service for teacher profile management.

    Handles teacher-specific settings like classes taught
    and default preferences for AI responses.
    """

    async def get_profile(self, user_id: str) -> TeacherProfileResponse | None:
        """Get teacher profile by user ID.

        Args:
            user_id: User identifier

        Returns:
            Teacher profile or None if not found
        """
        pass

    async def get_or_create_profile(self, user_id: str) -> TeacherProfileResponse:
        """Get existing profile or create with defaults.

        Args:
            user_id: User identifier

        Returns:
            Existing or newly created teacher profile

        Defaults:
            - classes_taught: empty list
            - analogy_enabled: True
            - realworld_enabled: True
        """
        pass

    async def update_profile(
        self,
        user_id: str,
        data: TeacherProfileRequest,
    ) -> TeacherProfileResponse:
        """Update teacher profile settings.

        Args:
            user_id: User identifier
            data: Profile update data

        Returns:
            Updated teacher profile

        Behavior:
            Creates profile if it doesn't exist
        """
        pass

    async def get_analogy_default(self, user_id: str) -> bool:
        """Get teacher's analogy preference.

        Args:
            user_id: User identifier

        Returns:
            True if analogies should be enabled by default
        """
        pass

    async def get_realworld_default(self, user_id: str) -> bool:
        """Get teacher's real-world context preference.

        Args:
            user_id: User identifier

        Returns:
            True if real-world context should be enabled by default
        """
        pass
