"""Seed curriculum metadata (grades + subjects).

Run with: make seed
"""

import asyncio
import uuid

from sqlalchemy import select

from somaai.db.models import CurriculumMetadata
from somaai.db.session import async_session_maker

METADATA = [
    # Grades
    {"type": "grade", "key": "P6", "name": "Primary 6", "display_order": 6},
    {"type": "grade", "key": "S1", "name": "Senior 1", "display_order": 7},
    {"type": "grade", "key": "S2", "name": "Senior 2", "display_order": 8},
    {"type": "grade", "key": "S3", "name": "Senior 3", "display_order": 9},
    {"type": "grade", "key": "S4", "name": "Senior 4", "display_order": 10},
    {"type": "grade", "key": "S5", "name": "Senior 5", "display_order": 11},
    {"type": "grade", "key": "S6", "name": "Senior 6", "display_order": 12},
    # Subjects
    {"type": "subject", "key": "computer_science", "name": "Computer Science", "display_order": 1},
    {"type": "subject", "key": "mathematics", "name": "Mathematics", "display_order": 2},
    {"type": "subject", "key": "english", "name": "English", "display_order": 3},
    {"type": "subject", "key": "kinyarwanda", "name": "Kinyarwanda", "display_order": 4},
    {"type": "subject", "key": "science", "name": "Science", "display_order": 5},
]


async def upsert_metadata(session):
    existing = await session.execute(select(CurriculumMetadata.key))
    existing_keys = {row[0] for row in existing.all()}

    for item in METADATA:
        if item["key"] in existing_keys:
            # Update existing
            result = await session.execute(
                select(CurriculumMetadata).where(
                    CurriculumMetadata.key == item["key"]
                )
            )
            entry = result.scalar_one()
            entry.name = item["name"]
            entry.type = item["type"]
            entry.display_order = item["display_order"]
            entry.is_active = True
        else:
            # Create new
            session.add(
                CurriculumMetadata(
                    id=str(uuid.uuid4()),
                    is_active=True,
                    **item,
                )
            )


async def main():
    async with async_session_maker() as session:
        await upsert_metadata(session)
        await session.commit()

    print("Seeded curriculum metadata (grades + subjects)")


if __name__ == "__main__":
    asyncio.run(main())
