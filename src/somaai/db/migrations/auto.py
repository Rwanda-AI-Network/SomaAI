"""Automated migration management."""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from somaai.settings import settings

logger = logging.getLogger(__name__)


def run_auto_migrations() -> None:
    """Run migrations and seed data automatically.

    This should be called during application startup in production to
    ensure the schema matches the code and initial data is present.
    """
    # 1. Determine alembic.ini path
    # When running in the container, it's in /app/alembic.ini
    # Locally, it's in the repo root.
    base_dir = Path(__file__).parent.parent.parent.parent.parent
    ini_path = base_dir / "alembic.ini"

    if not ini_path.exists():
        logger.warning(
            "alembic.ini not found at %s. Skipping auto-migrations.", ini_path
        )
        return

    logger.info("Running automated migrations...")
    try:
        cfg = Config(str(ini_path))
        # Ensure we use the current database URL
        # Alembic env.py already reads from settings, but we can override if needed.
        command.upgrade(cfg, "head")
        logger.info("Migrations completed successfully.")
    except Exception as e:
        logger.error("Failed to run automated migrations: %s", e)
        # In production, we might want to fail the startup
        if settings.is_production:
            raise
