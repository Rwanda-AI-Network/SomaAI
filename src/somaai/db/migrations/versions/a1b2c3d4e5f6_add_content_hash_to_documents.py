"""add content_hash to documents

Revision ID: a1b2c3d4e5f6
Revises: 05f04246113d
Create Date: 2026-02-28 23:53:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "05f04246113d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_documents_content_hash"),
        "documents",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_content_hash"), table_name="documents")
    op.drop_column("documents", "content_hash")
