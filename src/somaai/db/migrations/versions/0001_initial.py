"""initial schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-03-08 20:00:00.000000

Single initial migration for all SomaAI tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- curriculum_metadata ---
    op.create_table(
        "curriculum_metadata",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_order", sa.Integer(), default=0),
        sa.Column("is_active", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_curriculum_metadata_type", "curriculum_metadata", ["type"])

    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("storage_backend", sa.String(50), default="local"),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("page_count", sa.Integer(), default=0),
        sa.Column("chunk_count", sa.Integer(), default=0),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_grade", "documents", ["grade"])
    op.create_index("ix_documents_subject", "documents", ["subject"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])

    # --- chunks ---
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), default="New Chat"),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False, default="general"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_actor_id", "conversations", ["actor_id"])

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("user_role", sa.String(20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sufficiency", sa.String(20), nullable=False, default="sufficient"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False, default="general"),
        sa.Column("analogy", sa.Text(), nullable=True),
        sa.Column("realworld_context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_actor_id", "messages", ["actor_id"])
    op.create_index("ix_messages_grade", "messages", ["grade"])
    op.create_index("ix_messages_subject", "messages", ["subject"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    # --- message_citations ---
    op.create_table(
        "message_citations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relevance_score", sa.Float(), default=0.0),
        sa.Column("order", sa.Integer(), default=0),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])

    # --- topics ---
    op.create_table(
        "topics",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("doc_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False, default=list),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topics_grade", "topics", ["grade"])
    op.create_index("ix_topics_subject", "topics", ["subject"])

    # --- teacher_profiles ---
    op.create_table(
        "teacher_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("teacher_id", sa.String(64), nullable=False, unique=True),
        sa.Column("classes_taught", sa.JSON(), default=list),
        sa.Column("analogy_enabled", sa.Boolean(), default=True),
        sa.Column("realworld_enabled", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teacher_profiles_teacher_id", "teacher_profiles", ["teacher_id"])

    # --- feedback ---
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("useful", sa.Boolean(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), default=list),
        sa.Column("user_role", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_actor_id", "feedback", ["actor_id"])
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"], unique=True)

    # --- quizzes ---
    op.create_table(
        "quizzes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("teacher_id", sa.String(64), nullable=False),
        sa.Column("topic_ids", sa.JSON(), nullable=False),
        sa.Column("grade", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("include_citations", sa.Boolean(), default=True),
        sa.Column("difficulty", sa.String(20), nullable=False),
        sa.Column("num_questions", sa.Integer(), nullable=False),
        sa.Column("include_answer_key", sa.Boolean(), default=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quizzes_teacher_id", "quizzes", ["teacher_id"])
    op.create_index("ix_quizzes_grade", "quizzes", ["grade"])
    op.create_index("ix_quizzes_subject", "quizzes", ["subject"])

    # --- quiz_items ---
    op.create_table(
        "quiz_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("quiz_id", sa.String(36), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answer_citations", sa.JSON(), default=list),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quiz_items_quiz_id", "quiz_items", ["quiz_id"])

    # --- jobs ---
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_name", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("progress_pct", sa.Integer(), default=0),
        sa.Column("result_id", sa.String(36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_table("quiz_items")
    op.drop_table("quizzes")
    op.drop_table("feedback")
    op.drop_table("teacher_profiles")
    op.drop_table("topics")
    op.drop_table("message_citations")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("curriculum_metadata")
    op.drop_table("jobs")
