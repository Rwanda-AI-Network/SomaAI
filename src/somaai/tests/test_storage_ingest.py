from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from somaai.main import app

client = TestClient(app)


@pytest.fixture
def mock_storage():
    with (
        patch("somaai.api.v1.endpoints.ingest.get_storage") as mock_ingest,
        patch("somaai.services.ingest_service.get_storage") as mock_service,
    ):
        storage_instance = AsyncMock()
        mock_ingest.return_value = storage_instance
        mock_service.return_value = storage_instance
        yield storage_instance


@pytest.fixture
def mock_enqueue():
    with patch(
        "somaai.services.ingest_service.enqueue_job", new_callable=AsyncMock
    ) as mock:
        mock.return_value = "test-job-id"
        yield mock


@pytest.fixture
def mock_db_crud():
    with patch(
        "somaai.services.ingest_service.crud.create_document", new_callable=AsyncMock
    ) as mock:
        yield mock


def test_ingest_from_storage_success(mock_storage, mock_enqueue, mock_db_crud):
    """Test successful ingestion of an existing storage file."""
    mock_storage.get_metadata.return_value = {
        "size": 1024 * 1024,
        "content_type": "application/pdf",
    }

    response = client.post(
        "/api/v1/ingest/storage",
        json={
            "storage_key": "raw/curriculum/math_s1.pdf",
            "grade": "S1",
            "subject": "mathematics",
            "title": "Math S1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-id"
    assert "doc_id" in data

    # Verify metadata was checked
    mock_storage.get_metadata.assert_called_once_with("raw/curriculum/math_s1.pdf")

    # Verify job was enqueued with correct key
    mock_enqueue.assert_called_once()
    args = mock_enqueue.call_args[1]
    assert args["payload"]["storage_key"] == "raw/curriculum/math_s1.pdf"


def test_ingest_from_storage_not_found(mock_storage):
    """Test error when storage key does not exist."""
    mock_storage.get_metadata.return_value = None

    response = client.post(
        "/api/v1/ingest/storage",
        json={"storage_key": "missing.pdf", "grade": "S1", "subject": "mathematics"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_ingest_from_storage_large_file_success(
    mock_storage, mock_enqueue, mock_db_crud
):
    """Test that storage-based ingestion allows files larger than MAX_FILE_SIZE."""
    # Temporarily set a small limit to prove it's bypassed
    with patch("somaai.api.v1.endpoints.ingest.MAX_FILE_SIZE", 500):
        mock_storage.get_metadata.return_value = {"size": 1000}

        response = client.post(
            "/api/v1/ingest/storage",
            json={"storage_key": "large.pdf", "grade": "S1", "subject": "mathematics"},
        )

        assert response.status_code == 200
        assert mock_enqueue.called


def test_ingest_from_storage_invalid_extension(mock_storage):
    """Test error with unsupported file extension."""
    mock_storage.get_metadata.return_value = {"size": 100}

    response = client.post(
        "/api/v1/ingest/storage",
        json={"storage_key": "malicious.exe", "grade": "S1", "subject": "mathematics"},
    )

    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"].lower()
