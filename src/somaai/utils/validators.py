"""DB-driven validation for curriculum metadata.

Instead of hardcoded enums, grades and subjects are validated against
the Grade/Subject DB tables via MetaService (which caches responses
in L1 in-process + L2 Redis).  Adding a new grade or subject only
requires a DB insert — no code deployment needed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def validate_grade(db: AsyncSession, grade: str) -> str:
    """Validate that *grade* exists in the Grade table.

    Returns the normalised (uppercased) grade ID.

    Raises:
        HTTPException 422 if the grade is unknown.
    """
    from somaai.modules.meta.service import MetaService

    grade = grade.upper()
    service = MetaService(db)
    grades = await service.get_grades()
    valid_ids = {g.id for g in grades} if grades and hasattr(grades[0], "id") else {
        g["id"] for g in grades
    }
    if grade not in valid_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Grade '{grade}' not found. Valid grades: {sorted(valid_ids)}",
        )
    return grade


async def validate_subject(db: AsyncSession, subject: str) -> str:
    """Validate that *subject* exists in the Subject table.

    Returns the normalised (lowercased) subject ID.

    Raises:
        HTTPException 422 if the subject is unknown.
    """
    from somaai.modules.meta.service import MetaService

    subject = subject.lower()
    service = MetaService(db)
    subjects = await service.get_subjects()
    valid_ids = {s.id for s in subjects} if subjects and hasattr(subjects[0], "id") else {
        s["id"] for s in subjects
    }
    if subject not in valid_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Subject '{subject}' not found. Valid subjects: {sorted(valid_ids)}",
        )
    return subject
