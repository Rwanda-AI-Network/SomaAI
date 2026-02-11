#!/usr/bin/env python3
"""CLI tool for testing RAG retrieval locally.

Usage:
    python scripts/test_retrieval.py "What is photosynthesis?" --grade S2
    python scripts/test_retrieval.py "Pythagorean theorem" --grade S3 --top-k 5
    python scripts/test_retrieval.py "scheduling queues" --grade S6 --debug

Requires:
    - Qdrant running locally (docker-compose up qdrant)
    - Documents ingested into the collection
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def test_retrieval(
    query: str,
    grade: str,
    subject: str | None,
    top_k: int,
    debug: bool,
) -> None:
    """Run a test retrieval and display results."""
    from somaai.modules.rag.retriever import Retriever
    from somaai.settings import settings

    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

    retriever = Retriever(settings)

    print(f"\n{'=' * 60}")
    print("🔍 Testing retrieval")
    print(f"   Query:   {query}")
    print(f"   Grade:   {grade}")
    print(f"   Subject: {subject or '(none)'}")
    print(f"   Top K:   {top_k}")
    print(f"   Qdrant:  {settings.qdrant_url}")
    print(f"   Collection: {settings.qdrant_collection_name}")
    print(f"{'=' * 60}\n")

    # Test basic health
    print("📡 Checking retriever health...")
    health = await retriever.health_check()
    print(f"   Status: {health.get('status')}")
    if health.get("status") != "healthy":
        print(f"   Error: {health.get('error')}")
        print("\n❌ Qdrant is not reachable. Is it running?")
        print("   Try: docker-compose up qdrant")
        return

    # Run retrieval
    print("\n📚 Retrieving documents...")
    docs = await retriever.retrieve(
        query=query,
        top_k=top_k,
        grade=grade,
        subject=subject,
    )

    if not docs:
        print("\n⚠️  No documents found!")
        print("   Possible causes:")
        print("   1. No documents ingested for this grade")
        print("   2. Query doesn't match any content")
        print("   3. Collection is empty")

        # Try without filters
        print("\n🔄 Retrying without grade filter...")
        docs = await retriever.retrieve(
            query=query, top_k=top_k, grade=None, subject=None
        )
        if docs:
            print(f"   Found {len(docs)} docs without filters")
        else:
            print("   Still no docs. Collection may be empty.")
            return

    print(f"\n✅ Found {len(docs)} documents\n")

    for i, doc in enumerate(docs):
        score = doc.get("score", 0)
        metadata = doc.get("metadata", {})
        content = doc.get("content", "")

        # Score quality indicator
        if score >= 0.7:
            quality = "🟢"
        elif score >= 0.4:
            quality = "🟡"
        else:
            quality = "🔴"

        print(f"{'─' * 60}")
        print(f"  [{i + 1}] {quality} Score: {score:.4f}")
        print(f"      Title: {metadata.get('title', 'Unknown')}")
        grade_val = metadata.get('grade', '?')
        subj_val = metadata.get('subject', '?')
        print(f"      Grade: {grade_val} | Subject: {subj_val}")
        p_start = metadata.get('page_start', '?')
        p_end = metadata.get('page_end', '?')
        print(f"      Pages: {p_start}-{p_end}")
        if metadata.get("section_title"):
            print(f"      Section: {metadata['section_title']}")
        if metadata.get("fallback_level"):
            print(f"      ⚠️  Fallback level: {metadata['fallback_level']}")
        print(f"      Content: {content[:150]}...")
        print()

    # Also test retrieve_for_context
    print(f"\n{'=' * 60}")
    print("📝 Testing retrieve_for_context (full pipeline input)...")
    included_docs, context_str = await retriever.retrieve_for_context(
        query=query,
        grade=grade,
        subject=subject or "general",
    )
    print(f"   Docs included in context: {len(included_docs)}")
    ctx_len = len(context_str)
    print(f"   Context length: {ctx_len} chars (~{ctx_len // 4} tokens)")
    if context_str:
        print("\n   Context preview (first 300 chars):")
        print(f"   {context_str[:300]}...")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Test RAG retrieval locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "What is photosynthesis?" --grade S2
  %(prog)s "linear equations" --grade S3 --top-k 10
  %(prog)s "scheduling queues" --grade S6 --debug
        """,
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--grade", default="S1", help="Grade level (default: S1)")
    parser.add_argument("--subject", default=None, help="Subject filter (optional)")
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Number of results (default: 5)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    asyncio.run(
        test_retrieval(
            query=args.query,
            grade=args.grade,
            subject=args.subject,
            top_k=args.top_k,
            debug=args.debug,
        )
    )


if __name__ == "__main__":
    main()
