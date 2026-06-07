"""One-time script to normalize grade/subject metadata in Qdrant.

Ensures all stored documents use canonical casing:
  - grade: UPPERCASE (P6, S1, S6) — matches GradeLevel enum
  - subject: lowercase (computer_science) — matches Subject enum

Usage:
    uv run python scripts/normalize_qdrant_metadata.py
    uv run python scripts/normalize_qdrant_metadata.py --url http://localhost:6333
    uv run python scripts/normalize_qdrant_metadata.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def normalize_metadata(
    qdrant_url: str = "http://localhost:6333",
    collection: str = "somaai_documents",
    dry_run: bool = False,
) -> None:
    """Normalize grade to UPPERCASE, subject to lowercase in Qdrant."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.error("qdrant-client not installed. Run: pip install qdrant-client")
        sys.exit(1)

    client = QdrantClient(url=qdrant_url)

    # Verify collection exists
    try:
        info = client.get_collection(collection)
        total_points = info.points_count
        logger.info("Collection '%s' has %d points", collection, total_points)
    except Exception as e:
        logger.error("Failed to access collection '%s': %s", collection, e)
        sys.exit(1)

    offset = None
    updated = 0
    scanned = 0

    while True:
        results, next_offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )

        if not results:
            break

        for point in results:
            scanned += 1
            payload = point.payload or {}
            # LangChain nests metadata under "metadata" key
            meta = payload.get("metadata", payload)

            changes = {}
            grade = meta.get("grade")
            if grade and isinstance(grade, str) and grade != grade.strip().upper():
                changes["metadata.grade"] = grade.strip().upper()

            subject = meta.get("subject")
            if (
                subject
                and isinstance(subject, str)
                and subject != subject.strip().lower()
            ):
                changes["metadata.subject"] = subject.strip().lower()

            if changes:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Would update point %s: %s",
                        point.id,
                        changes,
                    )
                else:
                    client.set_payload(
                        collection_name=collection,
                        payload=changes,
                        points=[point.id],
                    )
                    logger.info("Updated point %s: %s", point.id, changes)
                updated += 1

        offset = next_offset
        if offset is None:
            break

    action = "Would update" if dry_run else "Updated"
    logger.info(
        "\nDone. Scanned %d points, %s %d.",
        scanned,
        action,
        updated,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize grade/subject metadata in Qdrant"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:6333",
        help="Qdrant URL (default: http://localhost:6333)",
    )
    parser.add_argument(
        "--collection",
        default="somaai_documents",
        help="Collection name (default: somaai_documents)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )
    args = parser.parse_args()

    normalize_metadata(
        qdrant_url=args.url,
        collection=args.collection,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
