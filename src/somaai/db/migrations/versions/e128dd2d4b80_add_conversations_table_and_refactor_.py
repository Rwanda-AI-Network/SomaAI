"""add_conversations_table_and_refactor_messages

Revision ID: e128dd2d4b80
Revises: a1b2c3d4e5f6
Create Date: 2026-03-04 21:49:52.961027
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "e128dd2d4b80"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), server_default="New Chat"),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_conversations_actor_id", "conversations", ["actor_id"]
    )

    # 2. Add conversation_id FK to messages
    op.add_column(
        "messages",
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=True,  # Temporarily nullable for migration
        ),
    )
    op.create_index(
        "ix_messages_conversation_id", "messages", ["conversation_id"]
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )

    # 3. Make actor_id NOT NULL (was nullable)
    op.alter_column(
        "messages",
        "actor_id",
        existing_type=sa.String(64),
        nullable=False,
    )

    # 4. Drop old session_id column and its index
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_column("messages", "session_id")


def downgrade() -> None:
    # Reverse: re-add session_id, drop conversation_id, drop conversations table
    op.add_column(
        "messages",
        sa.Column("session_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_messages_session_id", "messages", ["session_id"]
    )

    op.alter_column(
        "messages",
        "actor_id",
        existing_type=sa.String(64),
        nullable=True,
    )

    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_column("messages", "conversation_id")

    op.drop_index("ix_conversations_actor_id", table_name="conversations")
    op.drop_table("conversations")
