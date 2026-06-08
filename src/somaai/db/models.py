"""Database models for SomaAI.

All models use SQLAlchemy ORM with async support.
Migrations managed via Alembic.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from somaai.db.base import Base


class CurriculumMetadata(Base):
    __tablename__ = "curriculum_metadata"

    id = Column(String(36), primary_key=True)
    type = Column(String(20), nullable=False, index=True)  # "grade" | "subject"
    key = Column(String(50), nullable=False, unique=True)  # "S6", "computer_science"
    name = Column(String(100), nullable=False)  # "Secondary 6", "Computer Science"
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Document(Base):
    """Uploaded curriculum document.

    Stores document metadata and links to storage.
    Actual chunks are stored in Chunk table.
    """

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)
    storage_backend = Column(String(50), default="local")
    grade = Column(String(10), nullable=False, index=True)
    subject = Column(String(50), nullable=False, index=True)
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    status = Column(
        String(20), default="pending", index=True
    )  # pending, processing, completed, failed
    error_message = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hex digest
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Document chunk for vector search.

    A piece of a document used for embedding and retrieval.
    Links to the source document and page.
    """

    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True)
    document_id = Column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")
    message_citations = relationship("MessageCitation", back_populates="chunk")


class Conversation(Base):
    """Conversation container grouping related messages.

    Each conversation belongs to a single actor and has a grade/subject scope.
    """

    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)
    actor_id = Column(String(64), nullable=False, index=True)
    title = Column(String(255), default="New Chat")
    grade = Column(String(10), nullable=False)
    subject = Column(String(50), nullable=False, default="general")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """Chat message (query + response pair).

    Stores user questions and AI responses for history and feedback.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    conversation_id = Column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    actor_id = Column(String(64), nullable=False, index=True)
    user_role = Column(String(20), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sufficiency = Column(String(20), nullable=False, default="sufficient")
    confidence = Column(Float, nullable=True)
    grade = Column(String(10), nullable=False, index=True)
    subject = Column(String(50), nullable=False, default="general", index=True)
    analogy = Column(Text, nullable=True)
    realworld_context = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    citations = relationship(
        "MessageCitation", back_populates="message", cascade="all, delete-orphan"
    )
    feedback = relationship("Feedback", back_populates="message", uselist=False)


class MessageCitation(Base):
    """Citation linking a message to source chunks.

    Tracks which document chunks were used to generate a response.
    """

    __tablename__ = "message_citations"

    id = Column(String(36), primary_key=True)
    message_id = Column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id = Column(
        String(36), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    relevance_score = Column(Float, default=0.0)
    order = Column(Integer, default=0)
    snippet = Column(Text, nullable=True)

    # Relationships
    message = relationship("Message", back_populates="citations")
    chunk = relationship("Chunk", back_populates="message_citations")


class Topic(Base):
    """Curriculum topic for organization and quiz generation.

    Topics are path based.
    """

    __tablename__ = "topics"

    id = Column(String(36), primary_key=True)
    doc_id = Column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    title = Column(String(255), nullable=False)
    grade = Column(String(10), nullable=False, index=True)
    subject = Column(String(50), nullable=False, index=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    path = Column(JSON, nullable=False, default=list)
    # display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TeacherProfile(Base):
    """Teacher profile with settings and preferences.

    Stores teacher-specific configuration.
    """

    __tablename__ = "teacher_profiles"

    id = Column(String(36), primary_key=True)
    teacher_id = Column(String(64), nullable=False, unique=True, index=True)
    classes_taught = Column(JSON, default=list)
    analogy_enabled = Column(Boolean, default=True)
    realworld_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Feedback(Base):
    """Teacher feedback on AI responses.

    Used for quality improvement and analytics.
    """

    __tablename__ = "feedback"

    id = Column(String(36), primary_key=True)
    message_id = Column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        # unique=True, This will be unique after adding the authentication
    )
    # Actor ID for MVP to know who gave the feedback
    actor_id = Column(String(64), nullable=False, index=True)
    useful = Column(Boolean, nullable=False)
    text = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    user_role = Column(String(20), nullable=True)  # student or teacher
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    message = relationship("Message", back_populates="feedback")

    __table_args__ = (Index("ix_feedback_message_id", "message_id", unique=True),)


class Quiz(Base):
    """Generated quiz for teachers.

    Contains metadata; questions are in QuizItem.
    """

    __tablename__ = "quizzes"

    id = Column(String(36), primary_key=True)
    teacher_id = Column(String(64), nullable=False, index=True)
    topic_ids = Column(JSON, nullable=False)
    grade = Column(String(10), nullable=False, index=True)
    subject = Column(String(50), nullable=False, index=True)
    include_citations = Column(Boolean, default=True)
    difficulty = Column(String(20), nullable=False)
    num_questions = Column(Integer, nullable=False)
    include_answer_key = Column(Boolean, default=True)
    status = Column(String(20), default="pending")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "QuizItem", back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizItem(Base):
    """Single quiz question with answer.

    Generated question from curriculum content.
    """

    __tablename__ = "quiz_items"

    id = Column(String(36), primary_key=True)
    quiz_id = Column(
        String(36),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    answer_citations = Column(JSON, default=list)
    order = Column(Integer, nullable=False)
    options = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quiz = relationship("Quiz", back_populates="items")


class Job(Base):
    """Background job tracking.

    Stores status for async operations like ingestion and quiz generation.
    """

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    task_name = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(String(20), default="pending", index=True)
    progress_pct = Column(Integer, default=0)
    result_id = Column(String(36), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
