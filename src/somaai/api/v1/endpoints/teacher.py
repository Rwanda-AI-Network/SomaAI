"""Teacher profile endpoints."""

from fastapi import APIRouter

from somaai.contracts.teacher import TeacherProfileRequest, TeacherProfileResponse

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/profile", response_model=TeacherProfileResponse)
async def get_profile():
    """Get current teacher's profile.

    Returns teacher profile settings including:
    - Classes taught (grade + subject combinations)
    - Default analogy/real-world preferences

    Creates a default profile if none exists.
    """
    pass


@router.post("/profile", response_model=TeacherProfileResponse)
async def update_profile(
    data: TeacherProfileRequest,
):
    """Create or update teacher profile.

    Request body:
    - classes_taught: List of {grade, subject} objects
    - analogy_enabled: Enable analogies in responses by default
    - realworld_enabled: Enable real-world context by default

    These defaults are used when teacher doesn't specify in chat request.
    """
    pass
