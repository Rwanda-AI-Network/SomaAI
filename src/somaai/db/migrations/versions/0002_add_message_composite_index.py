"""add message composite index

Revision ID: 0002_message_index
Revises: 0001_initial
Create Date: 2026-03-17 16:15:00.000000

Adds a composite index to messages table for faster history retrieval.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0002_message_index"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ix_messages_actor_conversation_created(actor_id, conversation_id, created_at DESC)
    op.create_index(
        "ix_messages_actor_conversation_created",
        "messages",
        ["actor_id", "conversation_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_actor_conversation_created", table_name="messages")
