"""add performance indexes for message queries

Revision ID: a2b3c4d5e6f7
Revises: fd5cd1a7fa49
Create Date: 2026-03-07 14:30:00.000000

This migration adds composite indexes to optimize frequently-used query patterns:
1. Messages by actor + conversation + created_at (for list_messages)
2. Message citations by message_id (for citation retrieval)
3. Chunks by document_id (for citation joins)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'fd5cd1a7fa49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indexes for query optimization."""
    
    # Index 1: Optimize list_messages query
    # Query pattern: WHERE actor_id = ? AND conversation_id = ? ORDER BY created_at DESC
    # This composite index covers the entire query
    op.create_index(
        'ix_messages_actor_conversation_created',
        'messages',
        ['actor_id', 'conversation_id', 'created_at'],
        postgresql_ops={'created_at': 'DESC'}
    )
    
    # Index 2: Optimize message citation retrieval
    # Query pattern: WHERE message_id = ? ORDER BY order
    # Already has ix_message_citations_message_id, but add order column
    op.create_index(
        'ix_message_citations_message_order',
        'message_citations',
        ['message_id', 'order']
    )
    
    # Index 3: Optimize chunk lookups in citation joins
    # Query pattern: WHERE document_id = ?
    # This helps the 3-way join: MessageCitation -> Chunk -> Document
    op.create_index(
        'ix_chunks_document_id',
        'chunks',
        ['document_id']
    )


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index('ix_chunks_document_id', table_name='chunks')
    op.drop_index('ix_message_citations_message_order', table_name='message_citations')
    op.drop_index('ix_messages_actor_conversation_created', table_name='messages')

