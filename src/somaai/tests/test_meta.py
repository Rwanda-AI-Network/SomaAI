"""Tests for meta endpoints.

Tests for the curriculum metadata API: grades, subjects, and topics.
Uses the same sync TestClient pattern as test_chat.py.

Strategy:
- Seed data via async_session_maker (tables created by lifespan/init_db)
- Test each endpoint for correct responses, schema, ordering, filtering
- Test edge cases: empty DB, non-existent combinations, param validation
- Test cache behaviour via MetaService directly
"""

import asyncio
import time

from fastapi.testclient import TestClient

from somaai.db.models import CurriculumMetadata, Document, Topic
from somaai.db.session import async_session_maker
from somaai.modules.meta.service import (
    CACHE_TTL,
    _cache,
    _get_cached,
    _set_cached,
    invalidate_meta_cache,
)
from somaai.utils.ids import generate_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run async code from sync test."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _seed_grades():
    """Seed grade records and return their IDs."""
    async with async_session_maker() as db:
        grades = [
            CurriculumMetadata(
                id="P6", type="grade", key="P6", name="Primary 6", display_order=6
            ),
            CurriculumMetadata(
                id="S1", type="grade", key="S1", name="Senior 1", display_order=7
            ),
            CurriculumMetadata(
                id="S2", type="grade", key="S2", name="Senior 2", display_order=8
            ),
        ]
        for g in grades:
            db.add(g)
        await db.commit()
    return [g.key for g in grades]


async def _seed_subjects():
    """Seed subject records and return their IDs."""
    async with async_session_maker() as db:
        subjects = [
            CurriculumMetadata(
                id="mathematics",
                type="subject",
                key="mathematics",
                name="Mathematics",
                display_order=1,
            ),
            CurriculumMetadata(
                id="english",
                type="subject",
                key="english",
                name="English",
                display_order=2,
            ),
            CurriculumMetadata(
                id="science",
                type="subject",
                key="science",
                name="Science",
                display_order=3,
            ),
        ]
        for s in subjects:
            db.add(s)
        await db.commit()
    return [s.key for s in subjects]


async def _seed_document(grade: str, subject: str) -> str:
    """Seed a document and return its ID."""
    doc_id = generate_id()
    async with async_session_maker() as db:
        db.add(
            Document(
                id=doc_id,
                filename=f"{subject}_{grade}.pdf",
                title=f"{subject.title()} {grade} Book",
                storage_path=f"/uploads/{subject}_{grade}.pdf",
                grade=grade,
                subject=subject,
            )
        )
        await db.commit()
    return doc_id


async def _seed_topic(
    grade: str, subject: str, doc_id: str, title: str = "Cell Division"
) -> str:
    """Seed a topic and return its ID."""
    topic_id = generate_id()
    async with async_session_maker() as db:
        db.add(
            Topic(
                id=topic_id,
                doc_id=doc_id,
                title=title,
                grade=grade,
                subject=subject,
                page_start=1,
                page_end=10,
                path=["Chapter 1", title],
            )
        )
        await db.commit()
    return topic_id


async def _cleanup_all():
    """Remove all seeded data (topics → docs → subjects → grades)."""
    from sqlalchemy import delete

    from somaai.db.session import init_db

    await init_db()
    async with async_session_maker() as db:
        await db.execute(delete(Topic))
        await db.execute(delete(Document))
        await db.execute(delete(CurriculumMetadata))
        await db.commit()


# ============================================================================
# Grade Endpoint Tests
# ============================================================================


class TestGetGrades:
    """GET /api/v1/meta/metadata?type=grade — curriculum grade levels."""

    def setup_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def teardown_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def test_returns_empty_list_when_no_grades(self, client: TestClient):
        """Empty DB → empty list, not an error."""
        response = client.get("/api/v1/meta/metadata?type=grade")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_seeded_grades(self, client: TestClient):
        """Seeded grades appear in response."""
        _run(_seed_grades())
        response = client.get("/api/v1/meta/metadata?type=grade")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        ids = {g["key"] for g in data}
        assert ids == {"P6", "S1", "S2"}

    def test_response_schema(self, client: TestClient):
        """Each grade has id, name, display_order, level."""
        _run(_seed_grades())
        data = client.get("/api/v1/meta/metadata?type=grade").json()
        for grade in data:
            assert isinstance(grade["id"], str)
            assert isinstance(grade["key"], str)
            assert isinstance(grade["name"], str)
            assert isinstance(grade["display_order"], int)

    def test_sorted_by_display_order(self, client: TestClient):
        """Grades are returned in ascending display_order."""
        _run(_seed_grades())
        data = client.get("/api/v1/meta/metadata?type=grade").json()
        orders = [g["display_order"] for g in data]
        assert orders == sorted(orders), f"Not sorted: {orders}"

    def test_no_duplicate_ids(self, client: TestClient):
        """Grade IDs must be unique."""
        _run(_seed_grades())
        data = client.get("/api/v1/meta/metadata?type=grade").json()
        ids = [g["key"] for g in data]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"


# ============================================================================
# Subject Endpoint Tests
# ============================================================================


class TestGetSubjects:
    """GET /api/v1/meta/metadata?type=subject — curriculum subjects."""

    def setup_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def teardown_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def test_returns_all_subjects_without_filter(self, client: TestClient):
        """No grade param → all subjects returned."""
        _run(_seed_subjects())
        data = client.get("/api/v1/meta/metadata?type=subject").json()
        assert len(data) == 3

    def test_response_schema(self, client: TestClient):
        """Each subject has id, name, display_order, icon."""
        _run(_seed_subjects())
        data = client.get("/api/v1/meta/metadata?type=subject").json()
        for s in data:
            assert isinstance(s["id"], str)
            assert isinstance(s["key"], str)
            assert isinstance(s["name"], str)
            assert isinstance(s["display_order"], int)

    def test_sorted_by_display_order(self, client: TestClient):
        """Subjects returned in ascending display_order."""
        _run(_seed_subjects())
        data = client.get("/api/v1/meta/metadata?type=subject").json()
        orders = [s["display_order"] for s in data]
        assert orders == sorted(orders)

    def test_grade_filter_returns_subjects_with_documents(self, client: TestClient):
        """?grade=S2 returns only subjects with ingested documents."""
        _run(_seed_subjects())
        _run(_seed_document("S2", "science"))

        data = client.get("/api/v1/meta/metadata?type=subject&only_with_docs=true").json()
        ids = [s["id"] for s in data]
        assert "science" in ids

    def test_grade_filter_cold_start_returns_all(self, client: TestClient):
        """No documents for grade → returns all subjects (cold start)."""
        _run(_seed_subjects())
        # No documents seeded — all subjects returned
        data = client.get("/api/v1/meta/metadata?type=subject").json()
        assert len(data) == 3  # All subjects

    def test_grade_filter_with_multiple_documents(self, client: TestClient):
        """Multiple docs for same grade → returns distinct subjects."""
        _run(_seed_subjects())
        _run(_seed_document("S2", "science"))
        _run(_seed_document("S2", "science"))  # Duplicate subject
        _run(_seed_document("S2", "mathematics"))

        data = client.get("/api/v1/meta/metadata?type=subject&only_with_docs=true").json()
        ids = [s["id"] for s in data]
        assert "science" in ids
        assert "mathematics" in ids
        # No duplicate subjects
        assert len(ids) == len(set(ids))

    def test_empty_when_not_seeded(self, client: TestClient):
        """No subjects in DB → empty list."""
        data = client.get("/api/v1/meta/metadata?type=subject").json()
        assert data == []


# ============================================================================
# Topic Endpoint Tests
# ============================================================================


class TestGetTopics:
    """GET /api/v1/meta/topics — curriculum topics."""

    def setup_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    def teardown_method(self):
        invalidate_meta_cache()
        _run(_cleanup_all())

    # --- Parameter validation ---

    def test_requires_both_params(self, client: TestClient):
        """Missing both grade and subject → 422."""
        assert client.get("/api/v1/meta/topics").status_code == 422

    def test_requires_subject(self, client: TestClient):
        """Missing subject → 422."""
        assert client.get("/api/v1/meta/topics?grade=S2").status_code == 422

    def test_requires_grade(self, client: TestClient):
        """Missing grade → 422."""
        r = client.get("/api/v1/meta/topics?subject=science")
        assert r.status_code == 422

    # --- Happy path ---

    def test_returns_seeded_topics(self, client: TestClient):
        """Returns topics for a grade+subject combination."""
        doc_id = _run(_seed_document("S2", "science"))
        _run(_seed_topic("S2", "science", doc_id, "Cell Division"))
        _run(_seed_topic("S2", "science", doc_id, "Photosynthesis"))

        data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        assert len(data) == 2
        titles = {t["title"] for t in data}
        assert titles == {"Cell Division", "Photosynthesis"}

    def test_response_schema(self, client: TestClient):
        """Topic response matches TopicResponse contract."""
        doc_id = _run(_seed_document("S2", "science"))
        _run(_seed_topic("S2", "science", doc_id))

        data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        topic = data[0]

        assert isinstance(topic["topic_id"], str)
        assert isinstance(topic["title"], str)
        assert topic["grade"] == "S2"
        assert topic["subject"] == "science"
        assert isinstance(topic["doc_id"], str)
        assert isinstance(topic["page_start"], int)
        assert isinstance(topic["page_end"], int)
        assert isinstance(topic["path"], list)
        assert isinstance(topic["document_count"], int)

    def test_document_count_field(self, client: TestClient):
        """document_count is 1 when topic has a doc, 0 otherwise."""
        doc_id = _run(_seed_document("S2", "science"))
        _run(_seed_topic("S2", "science", doc_id))

        data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        assert data[0]["document_count"] == 1

    def test_path_field_contains_hierarchy(self, client: TestClient):
        """path field contains topic hierarchy."""
        doc_id = _run(_seed_document("S2", "science"))
        _run(_seed_topic("S2", "science", doc_id, "Cell Division"))

        data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        assert data[0]["path"] == ["Chapter 1", "Cell Division"]

    # --- Filtering ---

    def test_filters_by_grade(self, client: TestClient):
        """Topics for S2 science ≠ topics for S1 science."""
        doc_s2 = _run(_seed_document("S2", "science"))
        doc_s1 = _run(_seed_document("S1", "science"))
        _run(_seed_topic("S2", "science", doc_s2, "Cell Division"))
        _run(_seed_topic("S1", "science", doc_s1, "Atoms"))

        s2_data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        s1_data = client.get("/api/v1/meta/topics?grade=S1&subject=science").json()

        assert len(s2_data) == 1
        assert s2_data[0]["title"] == "Cell Division"
        assert len(s1_data) == 1
        assert s1_data[0]["title"] == "Atoms"

    def test_filters_by_subject(self, client: TestClient):
        """Topics for S2 science ≠ topics for S2 mathematics."""
        doc_sci = _run(_seed_document("S2", "science"))
        doc_math = _run(_seed_document("S2", "mathematics"))
        _run(_seed_topic("S2", "science", doc_sci, "Cell Division"))
        _run(_seed_topic("S2", "mathematics", doc_math, "Algebra"))

        sci_data = client.get("/api/v1/meta/topics?grade=S2&subject=science").json()
        math_data = client.get(
            "/api/v1/meta/topics?grade=S2&subject=mathematics"
        ).json()

        assert len(sci_data) == 1
        assert sci_data[0]["title"] == "Cell Division"
        assert len(math_data) == 1
        assert math_data[0]["title"] == "Algebra"

    def test_empty_for_nonexistent_combination(self, client: TestClient):
        """No topics → empty list, not 404."""
        data = client.get("/api/v1/meta/topics?grade=S6&subject=music").json()
        assert data == []


# ============================================================================
# Cache Behaviour Tests
# ============================================================================


class TestMetaCache:
    """Verify in-process TTL cache correctness."""

    def setup_method(self):
        invalidate_meta_cache()

    def teardown_method(self):
        invalidate_meta_cache()

    def test_cache_stores_and_retrieves(self):
        """_set_cached stores; _get_cached retrieves before expiry."""
        _run(_set_cached("test_key", [1, 2, 3]))
        assert _run(_get_cached("test_key")) == [1, 2, 3]

    def test_cache_returns_none_after_expiry(self):
        """Expired entries return None."""
        # Manually insert with an already-expired timestamp
        _cache["expired"] = (time.monotonic() - 1, "stale")
        assert _run(_get_cached("expired")) is None
        assert "expired" not in _cache  # Cleaned up

    def test_invalidate_clears_all(self, client: TestClient):
        """invalidate_meta_cache removes all entries."""
        _run(_set_cached("a", 1))
        _run(_set_cached("b", 2))
        invalidate_meta_cache()
        assert _run(_get_cached("a")) is None
        assert _run(_get_cached("b")) is None

    def test_cache_ttl_is_5_minutes(self):
        """CACHE_TTL should be 300 seconds."""
        assert CACHE_TTL == 300

    def test_grades_are_cached_on_second_call(self, client: TestClient):
        """Second GET /grades uses cached data (no DB hit)."""
        _run(_seed_grades())
        # First call — populates cache
        data1 = client.get("/api/v1/meta/metadata?type=grade").json()
        assert _run(_get_cached("metadata:type=grade:only_docs=False")) is not None

        # Second call — should use cache
        data2 = client.get("/api/v1/meta/metadata?type=grade").json()
        assert data1 == data2
        _run(_cleanup_all())

    def test_subject_cache_key(self, client: TestClient):
        """Subject metadata uses metadata:type=subject cache key."""
        _run(_seed_subjects())
        client.get("/api/v1/meta/metadata?type=subject")

        assert _run(_get_cached("metadata:type=subject:only_docs=False")) is not None
        _run(_cleanup_all())

    def test_subjects_all_cache_key(self, client: TestClient):
        """Subjects without grade uses 'subjects:all' cache key."""
        _run(_seed_subjects())
        client.get("/api/v1/meta/metadata?type=subject")
        assert _run(_get_cached("metadata:type=subject:only_docs=False")) is not None
        _run(_cleanup_all())
