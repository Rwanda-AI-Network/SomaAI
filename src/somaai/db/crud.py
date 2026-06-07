"""CRUD operations for database models.

Provides async database operations for Job and Document models.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from somaai.db.models import CurriculumMetadata, Document, Job, Topic

# ====================
# Job CRUD Operations
# ====================


async def create_job(
    db: AsyncSession,
    job_id: str,
    task_name: str,
    payload: dict,
) -> Job:
    """Create a new job record.

    Args:
        db: Database session
        job_id: Unique job identifier
        task_name: Name of the task to execute
        payload: Task-specific payload data

    Returns:
        Created Job instance

    Raises:
        ConflictError: If job with same ID already exists
        ValidationError: If required fields are missing or invalid
    """
    from sqlalchemy.exc import IntegrityError

    from somaai.exceptions import ConflictError, ValidationError

    job = Job(
        id=job_id,
        task_name=task_name,
        payload=payload,
        status="pending",
        progress_pct=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    try:
        await db.commit()
        await db.refresh(job)
        return job
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e).lower()
        if "duplicate key" in error_msg or "unique constraint" in error_msg:
            raise ConflictError(f"Job with ID '{job_id}' already exists")
        elif "not null" in error_msg or "null value" in error_msg:
            raise ValidationError("Required field is missing")
        elif "foreign key" in error_msg:
            raise ValidationError("Referenced resource does not exist")
        else:
            # Unknown constraint violation - log and re-raise
            import logging

            logging.getLogger(__name__).error(
                "Database constraint violation",
                extra={"job_id": job_id, "error": str(e)},
                exc_info=True,
            )
            raise ValidationError("Invalid data provided")


async def get_job(db: AsyncSession, job_id: str) -> Job | None:
    """Get job by ID.

    Args:
        db: Database session
        job_id: Job identifier

    Returns:
        Job instance if found, None otherwise
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession,
    job_id: str,
    status: str,
    progress_pct: int = 0,
    result_id: str | None = None,
    error: str | None = None,
) -> Job | None:
    """Update job status.

    Args:
        db: Database session
        job_id: Job identifier
        status: New status value
        progress_pct: Progress percentage (0-100)
        result_id: Result ID if completed
        error: Error message if failed

    Returns:
        Updated Job instance if found, None otherwise
    """
    job = await get_job(db, job_id)
    if not job:
        return None

    job.status = status
    job.progress_pct = progress_pct
    job.result_id = result_id
    job.error = error

    if status == "running" and not job.started_at:
        job.started_at = datetime.now(timezone.utc)
    elif status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return job


async def update_job_progress(
    db: AsyncSession,
    job_id: str,
    progress_pct: int,
) -> Job | None:
    """Update job progress percentage.

    Args:
        db: Database session
        job_id: Job identifier
        progress_pct: Progress percentage (0-100)

    Returns:
        Updated Job instance if found, None otherwise
    """
    job = await get_job(db, job_id)
    if not job:
        return None

    job.progress_pct = progress_pct
    await db.commit()
    return job


async def get_pending_jobs(db: AsyncSession, limit: int = 10) -> list[Job]:
    """Get pending jobs for processing.

    Args:
        db: Database session
        limit: Maximum number of jobs to fetch

    Returns:
        List of pending Job instances
    """
    result = await db.execute(
        select(Job).where(Job.status == "pending").order_by(Job.created_at).limit(limit)
    )
    return list(result.scalars().all())


# ==========================
# Document CRUD Operations
# ==========================


async def create_document(
    db: AsyncSession,
    doc_id: str,
    filename: str,
    title: str,
    storage_path: str,
    grade: str,
    subject: str,
    storage_backend: str = "local",
    status: str = "pending",
    content_hash: str | None = None,
) -> Document:
    """Create a new document record.

    Args:
        db: Database session
        doc_id: Unique document identifier
        filename: Original filename
        title: Document title
        storage_path: Path to stored file
        grade: Grade level
        subject: Subject
        storage_backend: Storage backend used (local, minio, s3)
        status: Initial document status (default: pending)
        content_hash: SHA-256 hex digest for deduplication

    Returns:
        Created Document instance

    Raises:
        ConflictError: If document with same ID or content_hash already exists
        ValidationError: If required fields are missing or invalid
    """
    from sqlalchemy.exc import IntegrityError

    from somaai.exceptions import ConflictError, ValidationError

    doc = Document(
        id=doc_id,
        filename=filename,
        title=title,
        storage_path=storage_path,
        grade=grade,
        subject=subject,
        storage_backend=storage_backend,
        status=status,
        content_hash=content_hash,
    )
    db.add(doc)
    try:
        await db.commit()
        await db.refresh(doc)
        return doc
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e).lower()
        if "duplicate key" in error_msg or "unique constraint" in error_msg:
            if "content_hash" in error_msg:
                raise ConflictError("Document with identical content already exists")
            raise ConflictError(f"Document with ID '{doc_id}' already exists")
        elif "not null" in error_msg or "null value" in error_msg:
            raise ValidationError("Required field is missing")
        elif "foreign key" in error_msg:
            raise ValidationError("Referenced resource does not exist")
        else:
            # Unknown constraint violation - log and re-raise
            import logging

            logging.getLogger(__name__).error(
                "Database constraint violation",
                extra={"doc_id": doc_id, "error": str(e)},
                exc_info=True,
            )
            raise ValidationError("Invalid data provided")


async def get_document(db: AsyncSession, doc_id: str) -> Document | None:
    """Get document by ID.

    Args:
        db: Database session
        doc_id: Document identifier

    Returns:
        Document instance if found, None otherwise
    """
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def update_document_processed(
    db: AsyncSession,
    doc_id: str,
    page_count: int,
    chunk_count: int | None = None,
) -> Document | None:
    """Mark document as processed.

    Args:
        db: Database session
        doc_id: Document identifier
        page_count: Number of pages in document
        chunk_count: Number of chunks extracted

    Returns:
        Updated Document instance if found, None otherwise
    """
    doc = await get_document(db, doc_id)
    if not doc:
        return None

    doc.processed_at = datetime.now(timezone.utc)
    doc.page_count = page_count
    doc.status = "completed"
    if chunk_count is not None:
        doc.chunk_count = chunk_count

    await db.commit()
    return doc


async def update_document_status(
    db: AsyncSession,
    doc_id: str,
    status: str,
    error: str | None = None,
) -> Document | None:
    """Update document status and optional error message.

    Args:
        db: Database session
        doc_id: Document identifier
        status: New status (pending, processing, completed, failed)
        error: Optional error message on failure
    """
    doc = await get_document(db, doc_id)
    if not doc:
        return None

    doc.status = status
    if error:
        doc.error_message = error
    await db.commit()
    return doc


# ==========================
# Chunk CRUD Operations
# ==========================


async def create_chunks(
    db: AsyncSession,
    chunks: list[dict],
) -> list[str]:
    """Create chunk records for a document.

    Uses bulk insert for efficiency (single DB roundtrip).

    Args:
        db: Database session
        chunks: List of chunk dicts with keys:
            - id (chunk_id)
            - document_id (doc_id)
            - content
            - page_start
            - page_end
            - chunk_index
            - embedding_id (optional)

    Returns:
        List of created chunk IDs
    """
    from somaai.db.models import Chunk

    if not chunks:
        return []

    # Build all chunk objects first
    chunk_objects = [
        Chunk(
            id=chunk_data["id"],
            document_id=chunk_data["document_id"],
            content=chunk_data["content"],
            page_start=chunk_data["page_start"],
            page_end=chunk_data["page_end"],
            chunk_index=chunk_data["chunk_index"],
            embedding_id=chunk_data.get("embedding_id"),
        )
        for chunk_data in chunks
    ]

    # Bulk insert (single roundtrip)
    db.add_all(chunk_objects)
    await db.commit()

    return [c.id for c in chunk_objects]


async def get_chunk(db: AsyncSession, chunk_id: str):
    """Get chunk by ID.

    Args:
        db: Database session
        chunk_id: Chunk identifier

    Returns:
        Chunk instance if found, None otherwise
    """
    from somaai.db.models import Chunk

    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    return result.scalar_one_or_none()


async def get_chunks_by_document(db: AsyncSession, document_id: str) -> list:
    """Get all chunks for a document.

    Args:
        db: Database session
        document_id: Document identifier

    Returns:
        List of Chunk instances
    """
    from somaai.db.models import Chunk

    result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
    )
    return list(result.scalars().all())


# ==========================
# Meta CRUD Operations
# ==========================


async def get_all_metadata(
    db: AsyncSession, meta_type: str | None = None
) -> list[CurriculumMetadata]:
    """Get all curriculum metadata entries, optionally filtered by type.

    Args:
        db: Database session
        meta_type: Optional filter — 'grade' or 'subject'

    Returns:
        List of CurriculumMetadata instances sorted by display_order
    """
    query = select(CurriculumMetadata)
    if meta_type:
        query = query.where(CurriculumMetadata.type == meta_type)
    query = query.order_by(CurriculumMetadata.display_order)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_metadata(
    db: AsyncSession, metadata_data: dict
) -> CurriculumMetadata:
    """Create a new curriculum metadata entry.

    Raises:
        ConflictError: If entry with same key already exists
        ValidationError: If required fields are missing or invalid
    """
    from sqlalchemy.exc import IntegrityError

    from somaai.exceptions import ConflictError, ValidationError

    entry = CurriculumMetadata(**metadata_data)
    db.add(entry)
    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e).lower()
        if "duplicate key" in error_msg or "unique constraint" in error_msg:
            raise ConflictError(
                f"Metadata with key '{metadata_data.get('key')}' already exists"
            )
        elif "not null" in error_msg or "null value" in error_msg:
            raise ValidationError("Required field is missing")
        else:
            import logging

            logging.getLogger(__name__).error(
                "Database constraint violation",
                extra={"key": metadata_data.get("key"), "error": str(e)},
                exc_info=True,
            )
            raise ValidationError("Invalid data provided")


async def update_metadata(
    db: AsyncSession, metadata_id: str, metadata_data: dict
) -> CurriculumMetadata | None:
    """Update an existing curriculum metadata entry."""
    entry = await db.get(CurriculumMetadata, metadata_id)
    if not entry:
        return None
    for key, value in metadata_data.items():
        if value is not None:
            setattr(entry, key, value)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_metadata(db: AsyncSession, metadata_id: str) -> bool:
    """Delete a curriculum metadata entry."""
    entry = await db.get(CurriculumMetadata, metadata_id)
    if not entry:
        return False
    await db.delete(entry)
    await db.commit()
    return True


# async def get_subjects_for_grade(db: AsyncSession, grade: str) -> list[Subject]:
#     """Get subjects that have documents for a specific grade.

#     Falls back to all subjects on cold start (no documents ingested yet).

#     Args:
#         db: Database session
#         grade: Grade ID (e.g., 'S2')

#     Returns:
#         List of Subject instances
#     """
#     from sqlalchemy import distinct

#     # Find subjects with at least one document for this grade
#     doc_result = await db.execute(
#         select(distinct(Document.subject)).where(Document.grade == grade.upper())
#     )
#     subject_ids = [row[0] for row in doc_result.all()]

#     if not subject_ids:
#         # Cold start: no documents yet, return all subjects
#         return await get_all_subjects(db)

#     result = await db.execute(
#         select(Subject)
#         .where(Subject.id.in_(subject_ids))
#         .order_by(Subject.display_order)
#     )
#     return list(result.scalars().all())

# ==========================
# Meta CRUD Operations (derived from documents)
# ==========================


async def get_distinct_grades(db: AsyncSession) -> list[dict]:
    """Get grades that have at least one ingested document.

    Returns list of dicts with grade string, e.g. [{"grade": "S2"}, {"grade": "S6"}]
    """
    from sqlalchemy import distinct

    result = await db.execute(select(distinct(Document.grade)).order_by(Document.grade))
    return [row[0] for row in result.all()]


async def get_distinct_subjects(
    db: AsyncSession, grade: str | None = None
) -> list[dict]:
    """Get subjects that have at least one ingested document.

    Optionally filter by grade.
    """
    from sqlalchemy import distinct

    query = select(distinct(Document.subject))
    if grade:
        query = query.where(Document.grade == grade.upper())
    query = query.order_by(Document.subject)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


async def get_topics_by_grade_subject(
    db: AsyncSession, grade: str, subject: str
) -> list[Topic]:
    """Get topics for a grade+subject combination.

    Args:
        db: Database session
        grade: Grade ID (e.g., 'S2')
        subject: Subject ID (e.g., 'biology')

    Returns:
        List of Topic instances ordered by page_start
    """
    result = await db.execute(
        select(Topic)
        .where(Topic.grade == grade.upper(), Topic.subject == subject.lower())
        .order_by(Topic.page_start)
    )
    return list(result.scalars().all())


async def get_topic_by_id(db: AsyncSession, topic_id: str) -> Topic | None:
    """Get a single topic by ID.

    Args:
        db: Database session
        topic_id: Topic identifier

    Returns:
        Topic instance if found, None otherwise
    """
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    return result.scalar_one_or_none()


# ==========================
# Meta CRUD Operations (derived from documents) --- END
# ==========================


async def get_topics_by_ids(db: AsyncSession, topic_ids: list[str]) -> list[Topic]:
    """Get multiple topics by IDs.

    Args:
        db: Database session
        topic_ids: List of topic IDs

    Returns:
        List of Topic instances
    """
    if not topic_ids:
        return []
    result = await db.execute(
        select(Topic).where(Topic.id.in_(topic_ids)).order_by(Topic.page_start)
    )
    return list(result.scalars().all())


async def get_document_counts_by_subject(
    db: AsyncSession, grade: str | None = None
) -> dict[str, int]:
    """Get document count per subject, optionally filtered by grade.

    Args:
        db: Database session
        grade: Optional grade ID to filter by

    Returns:
        Dict mapping subject_id -> document count
    """
    from sqlalchemy import func as sqlfunc

    query = select(Document.subject, sqlfunc.count(Document.id))
    if grade:
        query = query.where(Document.grade == grade.upper())
    query = query.group_by(Document.subject)
    result = await db.execute(query)
    return dict(result.all())


async def create_topic(db: AsyncSession, topic_id: str, topic_data: dict) -> Topic:
    """Create a new topic.

    Raises:
        ConflictError: If topic with same ID already exists
        ValidationError: If required fields are missing or invalid
    """
    from sqlalchemy.exc import IntegrityError

    from somaai.exceptions import ConflictError, ValidationError

    topic = Topic(id=topic_id, **topic_data)
    db.add(topic)
    try:
        await db.commit()
        await db.refresh(topic)
        return topic
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e).lower()
        if "duplicate key" in error_msg or "unique constraint" in error_msg:
            raise ConflictError(f"Topic with ID '{topic_id}' already exists")
        elif "not null" in error_msg or "null value" in error_msg:
            raise ValidationError("Required field is missing")
        elif "foreign key" in error_msg:
            raise ValidationError("Referenced resource does not exist")
        else:
            import logging

            logging.getLogger(__name__).error(
                "Database constraint violation",
                extra={"topic_id": topic_id, "error": str(e)},
                exc_info=True,
            )
            raise ValidationError("Invalid data provided")


async def update_topic(
    db: AsyncSession, topic_id: str, topic_data: dict
) -> Topic | None:
    """Update an existing topic."""
    topic = await db.get(Topic, topic_id)
    if not topic:
        return None
    for key, value in topic_data.items():
        if value is not None:
            setattr(topic, key, value)
    await db.commit()
    await db.refresh(topic)
    return topic


async def delete_topic(db: AsyncSession, topic_id: str) -> bool:
    """Delete a topic."""
    topic = await db.get(Topic, topic_id)
    if not topic:
        return False
    await db.delete(topic)
    await db.commit()
    return True
