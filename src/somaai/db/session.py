"""Database session management.

Provides async database sessions for FastAPI dependency injection.
Supports both PostgreSQL (production) and SQLite (testing).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from somaai.settings import settings

# Create async engine
# Create async engine
db_host = (
    settings.database_url.split("@")[-1]
    if "@" in settings.database_url
    else "local/sqlite"
)
print(f"DEBUG: Connecting to DB URL: {db_host}")

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Usage with FastAPI:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_session)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables.

    Creates all tables defined in models.
    Use Alembic for production migrations.
    """
    from somaai.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections.

    Call on application shutdown.
    """
    await engine.dispose()
