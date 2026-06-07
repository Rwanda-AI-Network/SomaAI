"""DB-driven validation for curriculum metadata.

Grades and subjects are validated against the curriculum_metadata table
via MetaService (which caches responses in L1 in-process + L2 Redis).
Adding a new grade or subject only requires an API call — no deployment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def validate_grade(db: AsyncSession, grade: str) -> str:
    """Validate that *grade* exists in the curriculum_metadata table.

    Returns the normalised (uppercased) grade key.

    Raises:
        HTTPException 422 if the grade is unknown.
    """
    from somaai.modules.meta.service import MetaService

    grade = grade.upper()
    service = MetaService(db)
    entries = await service.get_metadata(meta_type="grade")
    valid_keys = {e.key for e in entries}
    if grade not in valid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Grade '{grade}' not found. Valid grades: {sorted(valid_keys)}",
        )
    return grade


async def validate_subject(db: AsyncSession, subject: str) -> str:
    """Validate that *subject* exists in the curriculum_metadata table.

    Returns the normalised (lowercased) subject key.

    Raises:
        HTTPException 422 if the subject is unknown.
    """
    from somaai.modules.meta.service import MetaService

    subject = subject.lower()
    service = MetaService(db)
    entries = await service.get_metadata(meta_type="subject")
    valid_keys = {e.key for e in entries}
    if subject not in valid_keys:
        msg = f"Subject '{subject}' not found. Valid subjects: {sorted(valid_keys)}"
        raise HTTPException(
            status_code=422,
            detail=msg,
        )
    return subject
