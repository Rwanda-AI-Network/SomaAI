import asyncio

from sqlalchemy import select

from somaai.db.models import Grade, Subject
from somaai.db.session import async_session_maker

GRADES = [
    {"id": "P6", "name": "Primary 6", "level": "primary", "display_order": 6},
    {"id": "S1", "name": "Senior 1", "level": "secondary", "display_order": 7},
    {"id": "S2", "name": "Senior 2", "level": "secondary", "display_order": 8},
    {"id": "S3", "name": "Senior 3", "level": "secondary", "display_order": 9},
    {"id": "S4", "name": "Senior 4", "level": "secondary", "display_order": 10},
    {"id": "S5", "name": "Senior 5", "level": "secondary", "display_order": 11},
    {"id": "S6", "name": "Senior 6", "level": "secondary", "display_order": 12},
]

SUBJECTS = [
    {"id": "computer_science", "name": "Computer Science", "icon": "cpu", "display_order": 1},
    {"id": "mathematics", "name": "Mathematics", "icon": "calculator", "display_order": 2},
    {"id": "english", "name": "English", "icon": "book", "display_order": 3},
    {"id": "kinyarwanda", "name": "Kinyarwanda", "icon": "message-circle", "display_order": 4},
    {"id": "science", "name": "Science", "icon": "flask-conical", "display_order": 5},
]


async def upsert_grades(session):
    existing = await session.execute(select(Grade.id))
    existing_ids = {row[0] for row in existing.all()}

    for g in GRADES:
        if g["id"] in existing_ids:
            # update minimal fields in case they changed
            grade = await session.get(Grade, g["id"])
            grade.name = g["name"]
            grade.level = g["level"]
            grade.display_order = g["display_order"]
        else:
            session.add(Grade(**g))


async def upsert_subjects(session):
    existing = await session.execute(select(Subject.id))
    existing_ids = {row[0] for row in existing.all()}

    for s in SUBJECTS:
        if s["id"] in existing_ids:
            subj = await session.get(Subject, s["id"])
            subj.name = s["name"]
            subj.icon = s.get("icon")
            subj.display_order = s["display_order"]
        else:
            session.add(Subject(**s))


async def main():
    async with async_session_maker() as session:
        await upsert_grades(session)
        await upsert_subjects(session)
        await session.commit()

    print("Seeded grades + subjects")


if __name__ == "__main__":
    asyncio.run(main())
