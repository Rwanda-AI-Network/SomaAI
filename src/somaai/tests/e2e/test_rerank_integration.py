import asyncio
import os
import sys

# Add src to path for standalone execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

import logging
from unittest.mock import AsyncMock

from somaai.modules.rag.pipelines import RAGPipeline
from somaai.settings import settings

logging.basicConfig(level=logging.INFO)


async def test_reranker_real_pipeline():
    # Setup mock retriever to avoid Qdrant dependency
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_for_context.return_value = (
        [
            {"content": "Doc 1 content", "metadata": {"doc_id": "1"}, "score": 0.5},
            {"content": "Doc 2 content", "metadata": {"doc_id": "2"}, "score": 0.4},
            {"content": "Doc 3 content", "metadata": {"doc_id": "3"}, "score": 0.3},
        ],
        "Context string...",
    )

    # Instantiate pipeline
    pipeline = RAGPipeline(settings=settings)
    # Inject mock retriever
    pipeline.retriever = mock_retriever

    # Mock generator to avoid LLM call
    pipeline.generator = AsyncMock()
    pipeline.generator.generate.return_value = {
        "answer": "Generated answer",
        "sufficiency": "sufficient",
    }

    print("\n--- Running Real RAG Pipeline with Patched Retriever ---")
    await pipeline.run(query="test query", grade="S1", subject="science")

    # Verify Reranker was called and modified scores
    # We can inspect the arguments passed to the generator, as it receives the
    # 'retrieved_docs' which should be the *reranked* docs.
    call_args = pipeline.generator.generate.call_args
    if call_args:
        kwargs = call_args.kwargs
        retrieved_docs = kwargs.get("retrieved_docs", [])
        print(f"\nRetrieved Docs passed to Generator: {len(retrieved_docs)}")
        for doc in retrieved_docs:
            print(
                f"Doc ID: {doc.get('metadata', {}).get('doc_id')}, "
                f"Rerank Score: {doc.get('rerank_score')}, "
                f"Reasoning: {doc.get('rerank_reasoning')}"
            )

        # Check if scores match simulated logic (0.95 descending)
        first_score = retrieved_docs[0].get("rerank_score")
        if retrieved_docs and str(first_score) == "0.95":
            print("\nSUCCESS: Reranking logic verified!")
        else:
            print("\nFAILURE: Reranking scores do not match expected simulation.")
    else:
        print("\nFAILURE: Generator was not called.")


if __name__ == "__main__":
    asyncio.run(test_reranker_real_pipeline())
