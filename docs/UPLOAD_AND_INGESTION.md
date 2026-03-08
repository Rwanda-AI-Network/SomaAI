# File Upload & Ingestion Guide

SomaAI provides two primary methods for bringing documents into the system: **Standard Ingestion** for small-to-medium files and **Chunked Upload** for large student books and documents (>50MB).

---

## 1. Standard Ingestion (`/api/v1/ingest`)

Used for direct uploads where the file can be sent in a single multipart request.

### Role
The "Easy Path". It handles receipt, validation, storage, and background task enqueuing in a single operation.

### Mechanics
1.  **Receipt**: FastAPI receives the multipart stream.
2.  **Validation**:
    - **Extension Check**: Basic check against `ALLOWED_EXTENSIONS`.
    - **Security Audit**: High-speed scan for PDF signatures and malicious JavaScript.
3.  **Streaming Hashing (O(64KB) RAM)**:
    - The file is streamed into the storage backend.
    - **Single-Pass Hashing**: As the bits are written to S3/MinIO, a SHA-256 digest is computed in-flight.
4.  **Deduplication**:
    - Before finalizing the save, the system checks if a file with the same SHA-256 already exists.
    - If it exists, the new upload is discarded, and the existing `object_key` is reused.
5.  **Enqueuing**: A background job is created in Redis/ARQ for the [Ingestion Pipeline](./INGESTION_PIPELINE.md).

---

## 2. Chunked Upload (`/api/v1/upload/*`)

Designed for large curriculum documents. It overcomes timeout issues and allows for resumable uploads.

### Mechanics

#### Phase A: Initialization (`POST /init`)
- **Action**: Registers a new upload session in Redis.
- **Input**: `filename`, `total_size`, `total_chunks`.
- **Output**: `upload_id` (used for all subsequent calls).

#### Phase B: Chunk Streaming (`POST /chunk/{id}/{idx}`)
- **Action**: Uploads an individual slice of the file.
- **Storage**: Chunks are stored in a staging area (e.g., `_uploads/{upload_id}/chunk_0000X`).
- **Validation**: Ensures the `chunk_index` matches the expected range.

#### Phase C: Completion (`POST /complete/{id}`)
- **Assembly**: Triggered once all chunks are verified as present.
- **Server-Side Composition**: 
  - **MinIO**: Uses `compose_object` to merge chunks without moving data back to the server.
  - **S3**: Uses `multipart_upload` copy commands.
- **RAII Hashing**: Opens the assembled stream via `StorageStream` to compute the authoritative SHA-256 hash.
- **Final Move**: Moves the assembled file to its permanent location (`documents/{hash}.pdf`).
- **Cleanup**: Deletes all staging chunks in parallel.

---

## Comparison Matrix

| Feature | Standard Ingest (`/ingest`) | Chunked Upload (`/upload`) | Storage Ingest (`/ingest/storage`) |
| :--- | :--- | :--- | :--- |
| **Ideal For** | Files < 50MB | Files > 50MB | Pre-stored files |
| **Complexity** | 1 Request | 3+ Requests | 1 Request |
| **Resumability** | No | Yes | N/A |
| **Memory Usage** | O(Stream) | O(Stream) | O(1) Metadata check |
| **Max Size** | 100MB (Default) | Unlimited | Unlimited |
| **Deduplication** | Pre-save | Post-assembly | Implicit (task-side) |
| **Security** | Immediate | Post-assembly | Immediate |

---

## Key Patterns

### RAII Storage Streams
Both systems utilize the `StorageStream` context manager:
```python
async with storage.open(path) as stream:
    digest = await stream.hexdigest()
    # process bits...
# Connections are guaranteed to close here
```

### Content-Addressable Storage (CAS)
Files are always stored by their SHA-256 hash: `documents/{sha256}.{ext}`. This ensures that:
1.  Exactly one copy of a document exists across all grades/subjects.
2.  Database records for different grades can point to the same physical file.
3.  Storage costs are minimized.
