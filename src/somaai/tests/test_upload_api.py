"""Unit tests for file upload API endpoints.

Tests:
- Chunked upload session lifecycle (init, upload, complete, cancel)
- Single-pass ingestion with streaming hashing
- Error handling and bounds checking
"""

from __future__ import annotations

import hashlib
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from somaai.contracts.docs import IngestJobResponse
from somaai.main import app
from somaai.providers.storage import StorageStream

client = TestClient(app)


# ============================================================================
# Chunked Upload Tests
# ============================================================================


class TestChunkedUploadAPI:
    """Tests for /api/v1/upload endpoints."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis for upload session storage."""
        with patch(
            "somaai.api.v1.endpoints.chunked_upload._get_redis", new_callable=AsyncMock
        ) as m:
            redis = AsyncMock()
            m.return_value = redis
            yield redis

    @pytest.fixture
    def mock_storage(self):
        """Mock storage backend with AsyncMock for awaited methods."""
        with patch("somaai.api.v1.endpoints.chunked_upload._get_storage") as m:
            storage = MagicMock()
            storage.save = AsyncMock()
            storage.exists = AsyncMock(return_value=False)
            storage.compose_objects = AsyncMock(return_value=True)
            storage.delete = AsyncMock()
            storage.list_objects = AsyncMock(return_value=[])
            storage.open = MagicMock()  # open is a context manager, not awaited itself
            m.return_value = storage
            yield storage

    def test_init_upload_success(self, mock_redis):
        """Test initializing a chunked upload."""
        response = client.post(
            "/api/v1/upload/init",
            params={
                "filename": "test.pdf",
                "total_size": 1048576,
                "total_chunks": 2,
                "grade": "S1",
                "subject": "mathematics",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "upload_id" in data
        assert data["chunk_size"] == 5 * 1024 * 1024

        # Verify session saved to Redis
        assert mock_redis.setex.called

    def test_upload_chunk_success(self, mock_redis, mock_storage):
        """Test uploading a single chunk."""
        upload_id = "test-upload-id"
        session = {
            "upload_id": upload_id,
            "filename": "test.pdf",
            "total_size": 1048576,
            "total_chunks": 2,
            "grade": "S1",
            "subject": "mathematics",
            "title": "Test PDF",
            "received_chunks": [],
            "staging_prefix": f"_uploads/{upload_id}",
        }
        mock_redis.get.return_value = json.dumps(session)

        chunk_content = b"chunk data"
        response = client.post(
            f"/api/v1/upload/chunk/{upload_id}/0",
            files={"chunk": ("chunk_0", chunk_content)},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

        # Verify storage.save called
        mock_storage.save.assert_called_once()
        args, _ = mock_storage.save.call_args
        assert args[0] == chunk_content
        assert "chunk_00000" in args[1]

    def test_complete_upload_success(self, mock_redis, mock_storage):
        """Test completing upload (assembly + streaming hash)."""
        upload_id = "test-upload-id"
        session = {
            "upload_id": upload_id,
            "filename": "test.pdf",
            "total_size": 20,
            "total_chunks": 2,
            "grade": "S1",
            "subject": "mathematics",
            "title": "Test PDF",
            "received_chunks": [0, 1],
            "staging_prefix": f"_uploads/{upload_id}",
        }
        mock_redis.get.return_value = json.dumps(session)

        # Mock storage.open for two chunks
        chunk1 = b"chunk1"
        chunk2 = b"chunk2"

        mock_storage.open.side_effect = [
            StorageStream(io.BytesIO(chunk1)),
            StorageStream(io.BytesIO(chunk2)),
        ]
        mock_storage.exists.return_value = False
        mock_storage.compose_objects.return_value = True

        # Complete upload
        with patch(
            "somaai.api.v1.endpoints.chunked_upload.IngestionService.trigger_ingestion",
            new_callable=AsyncMock,
        ) as mock_ingest:
            mock_ingest.return_value = IngestJobResponse(
                job_id="job-123", doc_id="doc-123", status="pending", message="Started"
            )
            response = client.post(f"/api/v1/upload/complete/{upload_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job-123"

            # Verify assembly and cleanup
            assert mock_storage.compose_objects.called
            assert mock_storage.delete.call_count == 2
            assert mock_redis.delete.called

    def test_complete_upload_dedup_hit(self, mock_redis, mock_storage):
        """Test complete returns existing object if hash matches."""
        upload_id = "test-upload-id"
        session = {
            "upload_id": upload_id,
            "filename": "test.pdf",
            "total_chunks": 1,
            "grade": "S1",
            "subject": "mathematics",
            "title": "Test PDF",
            "received_chunks": [0],
            "staging_prefix": f"_uploads/{upload_id}",
        }
        mock_redis.get.return_value = json.dumps(session)
        mock_storage.open.return_value = StorageStream(io.BytesIO(b"data"))

        # Dedup hit
        mock_storage.exists.return_value = True

        with patch(
            "somaai.api.v1.endpoints.chunked_upload.IngestionService.trigger_ingestion",
            new_callable=AsyncMock,
        ) as mock_ingest:
            mock_ingest.return_value = IngestJobResponse(
                job_id="job-dedup",
                doc_id="doc-dedup",
                status="pending",
                message="Deduped",
            )
            response = client.post(f"/api/v1/upload/complete/{upload_id}")

            assert response.status_code == 200
            assert response.json()["job_id"] == "job-dedup"
            # Compose should NOT be called
            assert not mock_storage.compose_objects.called

    def test_cancel_upload_cleanup(self, mock_redis, mock_storage):
        """Test cancellation deletes all staging chunks."""
        upload_id = "test-upload-id"
        session = {"upload_id": upload_id, "staging_prefix": f"_uploads/{upload_id}"}
        mock_redis.get.return_value = json.dumps(session)
        mock_storage.list_objects.return_value = ["chunk1", "chunk2"]

        response = client.delete(f"/api/v1/upload/cancel/{upload_id}")

        assert response.status_code == 200
        # await asyncio.gather(*[_delete_obj(k) for k in staged_objects])
        assert mock_storage.delete.call_count == 2
        assert mock_redis.delete.called


# ============================================================================
# Ingest API Tests
# ============================================================================


class TestIngestAPI:
    """Tests for /api/v1/ingest endpoints."""

    @pytest.fixture
    def mock_storage(self):
        """Mock get_storage for ingest with AsyncMock methods."""
        with patch("somaai.api.v1.endpoints.ingest.get_storage") as m:
            storage = MagicMock()
            storage.save_deduplicated = AsyncMock()
            m.return_value = storage
            yield storage

    @pytest.fixture
    def mock_ingest_service(self):
        """Mock IngestionService.trigger_ingestion."""
        with patch(
            "somaai.api.v1.endpoints.ingest.IngestionService.trigger_ingestion",
            new_callable=AsyncMock,
        ) as m:
            m.return_value = IngestJobResponse(
                job_id="job-123", doc_id="doc-123", status="pending", message="Success"
            )
            yield m

    def test_ingest_success(self, mock_storage, mock_ingest_service):
        """Test ingestion with streaming hash and dedup."""
        # Use a real PDF signature to pass validate_file_content
        content = b"%PDF-1.7\ntest content"
        content_hash = hashlib.sha256(content).hexdigest()

        # save_deduplicated returns (key, hash, was_deduped)
        mock_storage.save_deduplicated.return_value = (
            f"documents/{content_hash}.pdf",
            content_hash,
            False,
        )

        response = client.post(
            "/api/v1/ingest",
            data={"grade": "S1", "subject": "social_studies", "title": "Test Doc"},
            files={"file": ("test.pdf", content, "application/pdf")},
        )

        if response.status_code != 200:
            pass  # Silent on success

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-123"

        # Verify single-pass hash saved
        mock_storage.save_deduplicated.assert_called_once()
        # Verify IngestionService called
        mock_ingest_service.assert_called_once()
        _, kwargs = mock_ingest_service.call_args
        assert kwargs["content_hash"] == content_hash
