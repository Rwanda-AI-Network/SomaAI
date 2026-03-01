"""Unit tests for object storage providers.

Tests MinioProvider and S3Provider with mocked clients to verify:
- save / save_deduplicated / get / get_stream / delete / exists / get_url
- list_objects / compose_objects
- SHA-256 content-hash deduplication logic
- Stream-based operations (O(1) memory verification)
"""

from __future__ import annotations

import hashlib
import io
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

# Robustly mock boto3 and botocore if they are missing in the environment
# to prevent ModuleNotFoundError when patching or importing S3Provider.
if "botocore" not in sys.modules:
    botocore = ModuleType("botocore")
    botocore.exceptions = ModuleType("botocore.exceptions")

    class ClientError(Exception):
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name

    botocore.exceptions.ClientError = ClientError
    sys.modules["botocore"] = botocore
    sys.modules["botocore.exceptions"] = botocore.exceptions

if "boto3" not in sys.modules:
    boto3 = ModuleType("boto3")
    boto3.Session = MagicMock
    boto3.client = MagicMock()
    sys.modules["boto3"] = boto3

import pytest

from somaai.providers.storage_minio import MinioProvider
from somaai.providers.storage_s3 import S3Provider

# ============================================================================
# MinioProvider Tests
# ============================================================================


class TestMinioProvider:
    """Tests for MinioProvider using a mocked minio.Minio client."""

    @pytest.fixture
    def mock_minio_client(self):
        """Create a mocked Minio client."""
        client = MagicMock()
        client.bucket_exists.return_value = True
        return client

    @pytest.fixture
    def provider(self, mock_minio_client):
        """Create a MinioProvider with mocked client, bypassing __init__."""
        p = object.__new__(MinioProvider)
        p.endpoint = "localhost:9000"
        p.access_key = "minioadmin"
        p.secret_key = "minioadmin"
        p.bucket = "test-bucket"
        p.secure = False
        p.client = mock_minio_client
        return p

    # --- save ---

    @pytest.mark.asyncio
    async def test_save_bytes(self, provider, mock_minio_client):
        """Test saving raw bytes to MinIO."""
        content = b"hello world bytes"

        result = await provider.save(content, "test/bytes.txt")

        assert result == "test/bytes.txt"
        mock_minio_client.put_object.assert_called_once()
        args, kwargs = mock_minio_client.put_object.call_args
        assert args[0] == "test-bucket"
        assert args[1] == "test/bytes.txt"
        assert kwargs["length"] == len(content)

    @pytest.mark.asyncio
    async def test_save_stream(self, provider, mock_minio_client):
        """Test saving a file-like object to MinIO."""
        content = b"hello world stream"
        stream = io.BytesIO(content)

        result = await provider.save(stream, "test/stream.txt")

        assert result == "test/stream.txt"
        mock_minio_client.put_object.assert_called_once()
        args, kwargs = mock_minio_client.put_object.call_args
        assert args[0] == "test-bucket"
        assert args[1] == "test/stream.txt"
        assert args[2] == stream
        assert kwargs["length"] == len(content)

    @pytest.mark.asyncio
    async def test_save_stream_uses_part_size_for_unknown_length(
        self, provider, mock_minio_client
    ):
        """When stream length is unknown (-1), part_size should be set for multipart."""

        class NonSeekableStream:
            """Stream that doesn't support seek."""

            def __init__(self, data):
                self._data = data
                self._pos = 0

            def read(self, n=-1):
                if n == -1:
                    result = self._data[self._pos :]
                else:
                    result = self._data[self._pos : self._pos + n]
                self._pos += len(result)
                return result

        stream = NonSeekableStream(b"data without seek")
        await provider.save(stream, "test/noseek.txt")

        _, kwargs = mock_minio_client.put_object.call_args
        assert kwargs["length"] == -1
        assert kwargs["part_size"] == 10 * 1024 * 1024

    # --- save_deduplicated ---

    @pytest.mark.asyncio
    async def test_save_deduplicated_stream(self, provider, mock_minio_client):
        """Test dedup upload with a stream."""
        content = b"stream content"
        expected_hash = hashlib.sha256(content).hexdigest()
        stream = io.BytesIO(content)

        # File doesn't exist yet
        mock_minio_client.stat_object.side_effect = Exception("not found")

        key, content_hash, was_deduped = await provider.save_deduplicated(
            stream, "documents", "test.pdf"
        )

        assert content_hash == expected_hash
        assert was_deduped is False
        mock_minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_deduplicated_new_file(self, provider, mock_minio_client):
        """Test dedup upload with a new file (no existing hash)."""
        content = b"unique content"
        expected_hash = hashlib.sha256(content).hexdigest()

        # File doesn't exist yet
        mock_minio_client.stat_object.side_effect = Exception("not found")

        key, content_hash, was_deduped = await provider.save_deduplicated(
            content, "documents", "test.pdf"
        )

        assert content_hash == expected_hash
        assert key == f"documents/{expected_hash}.pdf"
        assert was_deduped is False
        mock_minio_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_deduplicated_existing_file(self, provider, mock_minio_client):
        """Test dedup upload when file with same hash exists — should skip."""
        content = b"duplicate content"
        expected_hash = hashlib.sha256(content).hexdigest()

        # File already exists
        mock_minio_client.stat_object.return_value = MagicMock()

        key, content_hash, was_deduped = await provider.save_deduplicated(
            content, "documents", "test.pdf"
        )

        assert content_hash == expected_hash
        assert key == f"documents/{expected_hash}.pdf"
        assert was_deduped is True
        # put_object should NOT be called since file exists
        mock_minio_client.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_deduplicated_preserves_extension(
        self, provider, mock_minio_client
    ):
        """Object key extension comes from the original filename."""
        content = b"some data"
        expected_hash = hashlib.sha256(content).hexdigest()
        mock_minio_client.stat_object.side_effect = Exception("not found")

        key, _, _ = await provider.save_deduplicated(content, "docs", "REPORT.DOCX")

        assert key == f"docs/{expected_hash}.docx"  # lowercased

    # --- get ---

    @pytest.mark.asyncio
    async def test_get_existing_file(self, provider, mock_minio_client):
        """Test retrieving an existing file."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"file content"
        mock_minio_client.get_object.return_value = mock_response

        result = await provider.get("test/file.txt")

        assert result == b"file content"
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_file(self, provider, mock_minio_client):
        """Test retrieving a file that doesn't exist."""
        mock_minio_client.get_object.side_effect = Exception("NoSuchKey")

        result = await provider.get("nonexistent.txt")
        assert result is None

    # --- get_stream ---

    @pytest.mark.asyncio
    async def test_get_stream_returns_response_directly(
        self, provider, mock_minio_client
    ):
        """get_stream should return the raw MinIO response (a stream)."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"streamed data"
        mock_minio_client.get_object.return_value = mock_response

        stream = await provider.get_stream("test/file.txt")

        assert stream is mock_response
        # Stream should NOT be pre-read or closed by get_stream
        mock_response.read.assert_not_called()
        mock_response.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_stream_nonexistent_returns_none(
        self, provider, mock_minio_client
    ):
        """get_stream should return None for missing files."""
        mock_minio_client.get_object.side_effect = Exception("NoSuchKey: not found")

        result = await provider.get_stream("nonexistent.txt")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_stream_can_hash_without_full_memory_load(
        self, provider, mock_minio_client
    ):
        """Verify that streaming hash is possible — data read in chunks."""
        full_data = b"A" * 200_000  # 200KB
        pos = 0

        def chunk_read(n=-1):
            nonlocal pos
            if n == -1:
                result = full_data[pos:]
            else:
                result = full_data[pos : pos + n]
            pos += len(result)
            return result

        mock_response = MagicMock()
        mock_response.read = chunk_read
        mock_minio_client.get_object.return_value = mock_response

        stream = await provider.get_stream("test/big.pdf")

        # Hash in 64KB chunks (same as pipeline does)
        sha256 = hashlib.sha256()
        while block := stream.read(65536):
            sha256.update(block)

        assert sha256.hexdigest() == hashlib.sha256(full_data).hexdigest()

    # --- exists ---

    @pytest.mark.asyncio
    async def test_exists_true(self, provider, mock_minio_client):
        """Test exists returns True for existing file."""
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await provider.exists("test/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, provider, mock_minio_client):
        """Test exists returns False for non-existing file."""
        mock_minio_client.stat_object.side_effect = Exception("not found")

        result = await provider.exists("nonexistent.txt")
        assert result is False

    # --- delete ---

    @pytest.mark.asyncio
    async def test_delete_existing(self, provider, mock_minio_client):
        """Test deleting an existing file."""
        mock_minio_client.stat_object.return_value = MagicMock()

        result = await provider.delete("test/file.txt")

        assert result is True
        mock_minio_client.remove_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, provider, mock_minio_client):
        """Test deleting a non-existing file returns False."""
        mock_minio_client.stat_object.side_effect = Exception("not found")

        result = await provider.delete("nonexistent.txt")
        assert result is False

    # --- list_objects ---

    @pytest.mark.asyncio
    async def test_list_objects(self, provider, mock_minio_client):
        """Test listing objects with prefix."""
        obj1 = MagicMock()
        obj1.object_name = "docs/file1.pdf"
        obj2 = MagicMock()
        obj2.object_name = "docs/file2.pdf"
        mock_minio_client.list_objects.return_value = [obj1, obj2]

        result = await provider.list_objects("docs/")

        assert result == ["docs/file1.pdf", "docs/file2.pdf"]

    # --- compose_objects ---

    @pytest.mark.asyncio
    async def test_compose_objects_success(self, provider, mock_minio_client):
        """Test server-side composition of objects."""
        mock_minio_client.compose_object.return_value = None  # success

        result = await provider.compose_objects(
            dest_path="final/composed.pdf",
            src_paths=["_uploads/abc/chunk_00000", "_uploads/abc/chunk_00001"],
            content_type="application/pdf",
        )

        assert result is True
        mock_minio_client.compose_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_compose_objects_failure(self, provider, mock_minio_client):
        """Test compose returns False on error."""
        mock_minio_client.compose_object.side_effect = Exception("compose failed")

        result = await provider.compose_objects(
            dest_path="final/composed.pdf",
            src_paths=["chunk_0", "chunk_1"],
        )

        assert result is False

    # --- hash computation ---

    def test_compute_hash(self, provider):
        """Test SHA-256 hash computation."""
        content = b"test content"
        expected = hashlib.sha256(content).hexdigest()
        assert provider._compute_hash(content) == expected


# ============================================================================
# S3Provider Tests
# ============================================================================


class TestS3Provider:
    """Tests for S3Provider using mocked aioboto3 sessions."""

    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client returned by aioboto3 session.client()."""
        client = AsyncMock()
        # Mock the context manager behavior of self._session.client()
        client.__aenter__.return_value = client
        return client

    @pytest.fixture
    def provider(self, mock_s3_client):
        """Build S3Provider with mocked session."""
        from somaai.providers.storage_s3 import S3Provider

        p = object.__new__(S3Provider)
        p.bucket = "test-bucket"
        p.region = "us-east-1"
        p.access_key = "key"
        p.secret_key = "secret"
        p.endpoint_url = None

        mock_session = MagicMock()
        mock_session.client.return_value = mock_s3_client
        p._session = mock_session
        return p

    @pytest.mark.asyncio
    async def test_save_bytes(self, provider, mock_s3_client):
        """Test saving raw bytes to S3."""
        content = b"s3 bytes"
        await provider.save(content, "test/s3.txt")

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/s3.txt", Body=content
        )

    @pytest.mark.asyncio
    async def test_save_deduplicated_buffers_non_seekable_stream(
        self, provider, mock_s3_client
    ):
        """Verify save_deduplicated buffers non-seekable streams to temp file."""

        class NonSeekableStream:
            def __init__(self, data):
                self._data = data
                self._pos = 0

            def read(self, n=-1):
                res = (
                    self._data[self._pos :]
                    if n == -1
                    else self._data[self._pos : self._pos + n]
                )
                self._pos += len(res)
                return res

        content = b"non-seekable s3 data"
        stream = NonSeekableStream(content)
        expected_hash = hashlib.sha256(content).hexdigest()

        # Capture data in a side effect before it's closed
        captured_data = []

        def capture_put_object(**kwargs):
            body = kwargs["Body"]
            if hasattr(body, "read"):
                body.seek(0)
                captured_data.append(body.read())
            return AsyncMock()

        mock_s3_client.put_object.side_effect = capture_put_object

        # Mock exists to False
        with patch.object(S3Provider, "exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = False
            key, content_hash, _ = await provider.save_deduplicated(
                stream, "s3-docs", "file.pdf"
            )

        assert content_hash == expected_hash
        assert key == f"s3-docs/{expected_hash}.pdf"
        assert len(captured_data) == 1
        assert captured_data[0] == content

    @pytest.mark.asyncio
    async def test_get_existing_file(self, provider, mock_s3_client):
        """Test getting file content."""
        mock_body = AsyncMock()
        mock_body.read.return_value = b"s3 content"
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        result = await provider.get("key")
        assert result == b"s3 content"

    @pytest.mark.asyncio
    async def test_list_objects_paginates(self, provider, mock_s3_client):
        """Test S3 pagination optimization."""
        mock_paginator = MagicMock()

        async def _paginate(**kwargs):
            yield {"Contents": [{"Key": "a"}, {"Key": "b"}]}
            yield {"Contents": [{"Key": "c"}]}

        mock_paginator.paginate = _paginate

        # In our refactor, get_paginator is now awaited in storage_s3.py
        mock_s3_client.get_paginator = AsyncMock(return_value=mock_paginator)

        keys = await provider.list_objects("prefix/")
        assert keys == ["a", "b", "c"]
        mock_s3_client.get_paginator.assert_called_with("list_objects_v2")

    @pytest.mark.asyncio
    async def test_compose_objects_s3_specific(self, provider, mock_s3_client):
        """Test S3 Multipart Copy-based composition."""
        mock_s3_client.create_multipart_upload.return_value = {"UploadId": "up-123"}
        mock_s3_client.upload_part_copy.return_value = {
            "CopyPartResult": {"ETag": "tag"}
        }

        success = await provider.compose_objects("dest", ["src1", "src2"], "text/plain")

        assert success is True
        assert mock_s3_client.create_multipart_upload.called
        assert mock_s3_client.upload_part_copy.call_count == 2
        assert mock_s3_client.complete_multipart_upload.called

    @pytest.mark.asyncio
    async def test_get_stream_sync_fallback(self, provider):
        """Test get_stream uses the sync client correctly (and handles creds)."""

        # Mock the async session and credentials
        creds = MagicMock()
        creds.access_key = "AK"
        creds.secret_key = "SK"
        creds.token = "TK"
        provider._session.get_credentials = AsyncMock(return_value=creds)

        mock_body = MagicMock()
        mock_response = {"Body": mock_body}

        import boto3

        with patch.object(boto3, "client") as mock_boto_client:
            mock_sync_client = MagicMock()
            mock_boto_client.return_value = mock_sync_client
            mock_sync_client.get_object.return_value = mock_response

            stream = await provider.get_stream("key")

            assert stream is mock_body
            # Verify sync client created with right creds
            mock_boto_client.assert_called_once()
            _, kwargs = mock_boto_client.call_args
            assert kwargs["aws_access_key_id"] == "AK"
            assert kwargs["aws_secret_access_key"] == "SK"
            assert kwargs["aws_session_token"] == "TK"


# ============================================================================
# Storage Factory Tests
# ============================================================================


class TestStorageFactory:
    """Tests for get_storage() factory function."""

    def test_minio_backend(self):
        """Test factory returns MinioProvider for 'minio' backend."""
        with patch("somaai.settings.settings") as mock_settings:
            mock_settings.storage_backend = "minio"
            mock_settings.minio_endpoint = "localhost:9000"
            mock_settings.minio_access_key = "minioadmin"
            mock_settings.minio_secret_key = "minioadmin"
            mock_settings.minio_bucket = "test"
            mock_settings.minio_secure = False

            with patch("minio.Minio") as mock_minio_cls:
                mock_minio_cls.return_value.bucket_exists.return_value = True
                from somaai.providers.storage import get_storage

                storage = get_storage()
                assert isinstance(storage, MinioProvider)

    def test_unknown_backend_raises(self):
        """Test factory raises ValueError for unknown backend."""
        with patch("somaai.settings.settings") as mock_settings:
            mock_settings.storage_backend = "unknown"
            from somaai.providers.storage import get_storage

            with pytest.raises(ValueError, match="Unknown storage backend"):
                get_storage()


# ============================================================================
# Content-Hash Deduplication Logic Tests
# ============================================================================


class TestDeduplicationLogic:
    """Test the SHA-256 deduplication algorithm in isolation."""

    def test_same_content_produces_same_hash(self):
        """Two identical files should produce the same SHA-256 hash."""
        content1 = b"identical content for dedup testing"
        content2 = b"identical content for dedup testing"

        hash1 = hashlib.sha256(content1).hexdigest()
        hash2 = hashlib.sha256(content2).hexdigest()

        assert hash1 == hash2

    def test_different_content_produces_different_hash(self):
        """Two different files should produce different SHA-256 hashes."""
        content1 = b"file content version 1"
        content2 = b"file content version 2"

        hash1 = hashlib.sha256(content1).hexdigest()
        hash2 = hashlib.sha256(content2).hexdigest()

        assert hash1 != hash2

    def test_hash_used_as_object_key(self):
        """Object key should be directory/hash.extension format."""
        from pathlib import Path

        content = b"test file content"
        content_hash = hashlib.sha256(content).hexdigest()
        original_filename = "my_document.pdf"
        directory = "documents"

        ext = Path(original_filename).suffix.lower()
        object_key = f"{directory}/{content_hash}{ext}"

        assert object_key == f"documents/{content_hash}.pdf"
        assert len(content_hash) == 64  # SHA-256 is 64 hex chars

    def test_streaming_hash_matches_buffered_hash(self):
        """Streaming 64KB chunk hash must equal one-shot hash.

        This is the critical correctness property for the pipeline.
        """
        data = b"X" * 500_000  # 500KB

        # One-shot
        buffered_hash = hashlib.sha256(data).hexdigest()

        # Streaming
        sha256 = hashlib.sha256()
        stream = io.BytesIO(data)
        while chunk := stream.read(65536):
            sha256.update(chunk)
        streaming_hash = sha256.hexdigest()

        assert streaming_hash == buffered_hash


# ============================================================================
# StorageStream Context Manager Tests
# ============================================================================


class TestStorageStream:
    """Tests for the StorageStream RAII wrapper and open() context manager."""

    def test_close_calls_close_and_release_conn(self):
        """close() should call both close() and release_conn()."""
        from somaai.providers.storage import StorageStream

        raw = MagicMock()
        stream = StorageStream(raw)

        stream.close()

        raw.close.assert_called_once()
        raw.release_conn.assert_called_once()
        assert stream.closed is True

    def test_double_close_is_safe(self):
        """Calling close() twice must not error."""
        from somaai.providers.storage import StorageStream

        raw = MagicMock()
        stream = StorageStream(raw)

        stream.close()
        stream.close()  # should not raise

        # Only called once despite two close() calls
        raw.close.assert_called_once()

    def test_hexdigest_computes_correct_hash(self):
        """hexdigest() should match hashlib for same data."""
        from somaai.providers.storage import StorageStream

        data = b"principal engineer audit data"
        raw = io.BytesIO(data)
        stream = StorageStream(raw)

        result = stream.hexdigest()

        assert result == hashlib.sha256(data).hexdigest()

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exit(self):
        """async with should call close() on exit."""
        from somaai.providers.storage import StorageStream

        raw = MagicMock()
        raw.read = MagicMock(return_value=b"")

        async with StorageStream(raw) as stream:
            pass

        assert stream.closed is True
        raw.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_raises_file_not_found(self):
        """StorageBackend.open() raises FileNotFoundError for missing keys."""
        provider = MagicMock(spec=MinioProvider)
        provider.get_stream = AsyncMock(return_value=None)

        # Bind the real open() method to our mock
        from somaai.providers.storage import StorageBackend

        provider.open = StorageBackend.open.__get__(provider, type(provider))

        with pytest.raises(FileNotFoundError, match="Object not found"):
            async with provider.open("nonexistent/key"):
                pass

    @pytest.mark.asyncio
    async def test_open_yields_storage_stream(self):
        """StorageBackend.open() should yield a StorageStream wrapping the raw."""
        from somaai.providers.storage import StorageStream

        raw = MagicMock()
        raw.read = MagicMock(return_value=b"data")

        provider = MagicMock(spec=MinioProvider)
        provider.get_stream = AsyncMock(return_value=raw)

        from somaai.providers.storage import StorageBackend

        provider.open = StorageBackend.open.__get__(provider, type(provider))

        async with provider.open("test/key") as stream:
            assert isinstance(stream, StorageStream)
            assert stream.read() == b"data"

        assert stream.closed is True
