import asyncio
import logging

from sqlalchemy import select

from somaai.db.models import CurriculumMetadata
from somaai.db.session import async_session_maker

logger = logging.getLogger(__name__)

GRADES = [
    {"id": "P6", "name": "Primary 6", "type": "grade", "key": "P6", "display_order": 6},
    {"id": "S1", "name": "Senior 1", "type": "grade", "key": "S1", "display_order": 7},
    {"id": "S2", "name": "Senior 2", "type": "grade", "key": "S2", "display_order": 8},
    {"id": "S3", "name": "Senior 3", "type": "grade", "key": "S3", "display_order": 9},
    {"id": "S4", "name": "Senior 4", "type": "grade", "key": "S4", "display_order": 10},
    {"id": "S5", "name": "Senior 5", "type": "grade", "key": "S5", "display_order": 11},
    {"id": "S6", "name": "Senior 6", "type": "grade", "key": "S6", "display_order": 12},
]

SUBJECTS = [
    {
        "id": "computer_science",
        "name": "Computer Science",
        "type": "subject",
        "key": "computer_science",
        "display_order": 1,
    },
    {
        "id": "mathematics",
        "name": "Mathematics",
        "type": "subject",
        "key": "mathematics",
        "display_order": 2,
    },
    {
        "id": "english",
        "name": "English",
        "type": "subject",
        "key": "english",
        "display_order": 3,
    },
    {
        "id": "kinyarwanda",
        "name": "Kinyarwanda",
        "type": "subject",
        "key": "kinyarwanda",
        "display_order": 4,
    },
    {
        "id": "science",
        "name": "Science",
        "type": "subject",
        "key": "science",
        "display_order": 5,
    },
]


async def upsert_metadata(session, items):
    for item in items:
        # Use merge to handle both insert and update
        await session.merge(
            CurriculumMetadata(
                id=item["id"],
                type=item["type"],
                key=item["key"],
                name=item["name"],
                display_order=item["display_order"],
                is_active=True,
            )
        )


async def main():
    async with async_session_maker() as session:
        try:
            await upsert_metadata(session, GRADES)
            await upsert_metadata(session, SUBJECTS)
            await session.commit()
            print("Successfully seeded curriculum metadata (grades + subjects)")
        except Exception as e:
            await session.rollback()
            print(f"Error seeding metadata: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
