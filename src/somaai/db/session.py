"""Database session management.

Provides async database sessions for FastAPI dependency injection.
Supports both PostgreSQL (production) and SQLite (testing).
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from somaai.settings import settings

logger = logging.getLogger(__name__)

# Create async engine
db_host = settings.database_url.split("@")[-1] if "@" in settings.database_url else "local/sqlite"
logger.debug("Connecting to DB: %s", db_host)

# SQLite uses StaticPool which does not accept pool_size/max_overflow/pool_timeout.
# Only apply production pool settings for connection-based backends (PostgreSQL).
_pool_kwargs: dict = {}
if not settings.is_sqlite:
    _pool_kwargs = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_pre_ping": True,
    }

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo_sql,
    future=True,
    **_pool_kwargs,
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

    The session is yielded without auto-commit.  Every write path
    (CRUD helpers, service methods) calls ``await db.commit()``
    explicitly, so committing here would be a wasteful double round
    trip.  On exception the session is rolled back; cleanup is handled
    by the ``async with`` context manager.

    Usage with FastAPI:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_session)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


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
    logger.info("Database engine disposed")
