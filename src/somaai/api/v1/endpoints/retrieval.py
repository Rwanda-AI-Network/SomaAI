"""Retrieval endpoint for debug/admin search.

Provides direct access to document retrieval for debugging and testing.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.get("/search")
async def search_documents(
    query: str,
    grade: str = "S1",
    subject: str = "general",
    top_k: int = 5
):
    """Search documents with and without reranking for comparison.
    
    Args:
        query: Search query string
        grade: Grade level filter
        subject: Subject filter
        top_k: Number of results to return
        
    Returns:
        Comparison of retrieval vs reranking
    """
    from somaai.modules.rag.retriever import Retriever
    from somaai.modules.rag.reranker import get_reranker
    from somaai.settings import settings
    
    # 1. Retrieve
    retriever = Retriever(settings)
    raw_docs = await retriever.retrieve_with_fallback(
        query=query,
        grade=grade,
        subject=subject,
        top_k=20, # Retrieve more for reranking candidate pool
    )
    
    # 2. Rerank
    reranker = get_reranker()
    reranked_docs = []
    
    if raw_docs:
        reranked_docs = await reranker.rerank(
            query=query,
            documents=raw_docs, # Pass copies if needed, but dicts are mutable
            top_k=top_k,
        )
        
    return {
        "query": query,
        "filters": {"grade": grade, "subject": subject},
        "reranker_available": reranker.is_available,
        "results": {
            "retrieval_count": len(raw_docs),
            "reranked_count": len(reranked_docs),
            "top_reranked": [
                {
                    "content": d.get("content", "")[:200],
                    "score": float(d.get("rerank_score", 0)),
                    "original_score": float(d.get("score", 0)),
                    "doc_id": d.get("metadata", {}).get("doc_id"),
                }
                for d in reranked_docs
            ],
            # "raw_top_5": [ ... ] # Optional
        }
    }
