"""Teacher profile endpoint schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from somaai.contracts.common import GradeLevel, Subject


class ClassTaught(BaseModel):
    """A class (grade + subject combination) taught by a teacher."""

    grade: GradeLevel = Field(..., description="Grade level")
    subject: Subject = Field(..., description="Subject")


class TeacherProfileRequest(BaseModel):
    """Request body for POST /api/v1/teacher/profile.

    Creates or updates teacher profile settings.
    """

    classes_taught: list[ClassTaught] = Field(
        ...,
        min_length=1,
        description="List of classes (grade+subject) the teacher teaches",
    )
    analogy_enabled: bool = Field(
        True, description="Enable analogy explanations by default"
    )
    realworld_enabled: bool = Field(
        True, description="Enable real-world context by default"
    )


class TeacherProfileResponse(BaseModel):
    """Response for GET/POST /api/v1/teacher/profile.

    Current teacher profile settings.
    """

    profile_id: str = Field(..., description="Profile ID")
    teacher_id: str = Field(..., description="Associated teacher ID")
    classes_taught: list[ClassTaught] = Field(..., description="Classes taught")
    analogy_enabled: bool = Field(..., description="Analogy default setting")
    realworld_enabled: bool = Field(
        ..., description="Real-world context default setting"
    )
    created_at: datetime = Field(..., description="Profile creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
