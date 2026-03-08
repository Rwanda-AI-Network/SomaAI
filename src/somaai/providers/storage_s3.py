"""AWS S3 object storage backend.

Production storage backend using AWS S3.
Uses content-hash (SHA-256) based deduplication to prevent duplicate uploads.
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any, BinaryIO

from somaai.providers.storage import StorageBackend

logger = logging.getLogger(__name__)


class S3Provider(StorageBackend):
    """AWS S3 storage backend for production.

    Features:
    - Native async via aioboto3
    - SHA-256 content-hash deduplication
    - Presigned URLs for secure file access
    - IAM role or access key authentication
    - Custom endpoint support (for S3-compatible services)
    """

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """Initialize S3 client configuration.

        Args:
            bucket: S3 bucket name
            region: AWS region
            access_key: AWS access key ID (None = use IAM role)
            secret_key: AWS secret access key
            endpoint_url: Custom S3-compatible endpoint URL
        """
        import aioboto3

        from somaai.settings import settings

        self.bucket = bucket or settings.storage.s3_bucket
        self.region = region or settings.storage.s3_region
        self.access_key = access_key or settings.storage.s3_access_key
        if secret_key is not None:
            self.secret_key = (
                secret_key.get_secret_value()
                if hasattr(secret_key, "get_secret_value")
                else secret_key
            )
        else:
            self.secret_key = (
                settings.storage.s3_secret_key.get_secret_value()
                if settings.storage.s3_secret_key
                else None
            )
        self.endpoint_url = endpoint_url or settings.storage.s3_endpoint_url

        # Reuse a single session across all operations
        # aioboto3 sessions are lightweight and thread-safe
        self._session = aioboto3.Session()

        if not self.bucket:
            raise ValueError("S3_BUCKET must be set when using STORAGE_BACKEND=s3")

    @property
    def backend_type(self) -> str:
        return "s3"

    def _get_client_kwargs(self) -> dict:
        """Build boto3 client configuration."""
        kwargs: dict = {
            "service_name": "s3",
            "region_name": self.region,
        }
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    async def save(self, file: bytes | BinaryIO, path: str) -> str:
        """Save a file to S3.

        Args:
            file: File content as bytes or file-like object
            path: Object key (destination path in bucket)

        Returns:
            Object key of saved file
        """
        async with self._session.client(**self._get_client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=path,
                Body=file,
            )

        logger.debug(f"Saved object: s3://{self.bucket}/{path}")
        return path

    async def save_deduplicated(
        self,
        file: bytes | BinaryIO,
        directory: str,
        original_filename: str,
    ) -> tuple[str, str, bool]:
        """Upload with SHA-256 content-hash deduplication.

        Args:
            file: File content as bytes or file-like object
            directory: Target directory prefix (e.g. "documents")
            original_filename: Original filename (used for extension)

        Returns:
            Tuple of (object_key, content_hash, was_deduplicated)
        """
        import tempfile

        # Handle raw bytes
        if isinstance(file, bytes):
            content_hash = self._compute_hash(file)
            data_to_save = file
        else:
            # Handle file-like objects
            sha256 = hashlib.sha256()

            # Check if seekable. If not, we MUST buffer to compute hash first.
            try:
                file.seek(0)
                is_seekable = True
            except (AttributeError, io.UnsupportedOperation):
                is_seekable = False

            if is_seekable:
                # Seekable stream: hash in chunks, then rewind
                while chunk := file.read(65536):
                    sha256.update(chunk)
                content_hash = sha256.hexdigest()
                file.seek(0)
                data_to_save = file
            else:
                # Non-seekable stream: buffer to a spooled temporary file
                tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
                while chunk := file.read(65536):
                    sha256.update(chunk)
                    tmp.write(chunk)

                content_hash = sha256.hexdigest()
                tmp.seek(0)
                data_to_save = tmp

        # Build object key: directory/hash.ext
        ext = Path(original_filename).suffix.lower()
        object_key = f"{directory}/{content_hash}{ext}"

        # Check if object already exists (dedup)
        if await self.exists(object_key):
            logger.info(f"Dedup hit: {object_key} already exists, skipping upload")
            # Close the temp file if we created one
            if not isinstance(file, bytes) and not is_seekable:
                data_to_save.close()
            return object_key, content_hash, True

        # Upload using the base save method
        try:
            await self.save(data_to_save, object_key)
        finally:
            # Cleanup temp file if created
            if not isinstance(file, bytes) and not is_seekable:
                data_to_save.close()

        logger.info(f"Uploaded new object: s3://{self.bucket}/{object_key}")
        return object_key, content_hash, False

    async def get(self, path: str) -> bytes | None:
        """Retrieve file content from S3.

        Args:
            path: Object key

        Returns:
            File content as bytes, or None if not found
        """
        from botocore.exceptions import ClientError

        async with self._session.client(**self._get_client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=path)
                return await response["Body"].read()
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    return None
                raise

    async def get_stream(self, path: str) -> BinaryIO | None:
        """Retrieve file as a stream from S3.

        Uses synchronous boto3 in a thread to provide a true BinaryIO stream
        that can be consumed by sync functions (like text_extractor) without
        loading the entire file into RAM.
        """
        import asyncio

        import boto3
        from botocore.exceptions import ClientError

        # Use the session to get credentials and region for the sync client
        creds = await self._session.get_credentials()
        sync_client = boto3.client(
            "s3",
            aws_access_key_id=creds.access_key,
            aws_secret_access_key=creds.secret_key,
            aws_session_token=creds.token,
            region_name=self.region,
            endpoint_url=self.endpoint_url,
        )

        try:
            # We don't use 'with' here because the caller MUST own the lifecycle
            # of the response body. StorageStream handles the cleanup.
            response = await asyncio.to_thread(
                sync_client.get_object, Bucket=self.bucket, Key=path
            )
            return response["Body"]
        except ClientError as e:
            if e.response["Error"]["Code"] in ["NoSuchKey", "404"]:
                return None
            raise
        finally:
            # The client is a resource, but the body stream is what we care about.
            # Boto3 clients are stateless factories for requests, but we close
            # if the call failed. If successful, connection stays pooled.
            pass

    async def get_url(self, path: str, expires_in: int = 3600) -> str | None:
        """Get a presigned URL for the file from S3.

        Args:
            path: Object key
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL string, or None if not found or error
        """
        async with self._session.client(**self._get_client_kwargs()) as s3:
            try:
                # Check if exists first to avoid invalid URL generation
                if not await self.exists(path):
                    return None

                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": path},
                    ExpiresIn=expires_in,
                )
                return url
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for {path}: {e}")
                return None

    async def delete(self, path: str) -> bool:
        """Delete a file from S3.

        Args:
            path: Object key

        Returns:
            True if deleted, False if not found
        """
        if not await self.exists(path):
            return False

        async with self._session.client(**self._get_client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=path)
        return True

    async def get_metadata(self, path: str) -> dict[str, Any] | None:
        """Get object metadata from S3."""
        from botocore.exceptions import ClientError

        async with self._session.client(**self._get_client_kwargs()) as s3:
            try:
                stat = await s3.head_object(Bucket=self.bucket, Key=path)
                return {
                    "size": stat.get("ContentLength"),
                    "content_type": stat.get("ContentType"),
                    "last_modified": stat.get("LastModified"),
                    "metadata": stat.get("Metadata"),
                    "etag": stat.get("ETag"),
                }
            except ClientError:
                return None

    async def exists(self, path: str) -> bool:
        from botocore.exceptions import ClientError

        async with self._session.client(**self._get_client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=path)
                return True
            except ClientError:
                return False

    async def list_objects(self, prefix: str) -> list[str]:
        """List objects with a given prefix.

        Handles pagination correctly — S3 returns max 1000 objects per page.

        Args:
            prefix: Object key prefix to filter by

        Returns:
            List of object keys matching the prefix
        """
        keys: list[str] = []

        async with self._session.client(**self._get_client_kwargs()) as s3:
            paginator = await s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])

        return keys

    async def compose_objects(
        self,
        dest_path: str,
        src_paths: list[str],
        content_type: str | None = None,
    ) -> bool:
        """Combine multiple objects using S3 Multipart Upload with UploadPartCopy.

        This is a server-side operation that combines existing objects.
        """
        async with self._session.client(**self._get_client_kwargs()) as s3:
            # 1. Initiate Multipart Upload
            create_args = {"Bucket": self.bucket, "Key": dest_path}
            if content_type:
                create_args["ContentType"] = content_type

            mpu = await s3.create_multipart_upload(**create_args)
            upload_id = mpu["UploadId"]

            parts = []
            try:
                # 2. Upload Parts as Copies of existing objects
                for i, src_key in enumerate(src_paths, start=1):
                    copy_source = {"Bucket": self.bucket, "Key": src_key}
                    part = await s3.upload_part_copy(
                        Bucket=self.bucket,
                        Key=dest_path,
                        PartNumber=i,
                        UploadId=upload_id,
                        CopySource=copy_source,
                    )
                    parts.append(
                        {"PartNumber": i, "ETag": part["CopyPartResult"]["ETag"]}
                    )

                # 3. Complete Multipart Upload
                await s3.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=dest_path,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
                return True
            except Exception as e:
                logger.error(f"S3 compose failed for {dest_path}: {e}")
                # Abort if failed
                await s3.abort_multipart_upload(
                    Bucket=self.bucket, Key=dest_path, UploadId=upload_id
                )
                return False
