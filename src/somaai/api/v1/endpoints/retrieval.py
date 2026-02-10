"""Retrieval endpoint for debug/admin search.

Provides direct access to document retrieval for debugging and testing.
⚠️ DEBUG ONLY - Disabled in production for security.
"""

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def require_debug_mode():
    """Require debug mode to access this endpoint.
    
    In production, this endpoint is disabled for security.
    """
    from somaai.settings import settings
    
    if not settings.debug:
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available in debug mode"
        )
    return True


@router.get("/search")
async def search_documents(
    query: str,
    grade: str = "S1",
    subject: str = "general",
    top_k: int = 5,
    _: bool = Depends(require_debug_mode),  # Security check
):
    """Search documents with and without reranking for comparison.
    
    ⚠️ DEBUG ONLY - Disabled in production
    
    Args:
        query: Search query string
        grade: Grade level filter
        subject: Subject filter
        top_k: Number of results to return (max 20)
        
    Returns:
        Comparison of retrieval vs reranking
    """
    # Limit top_k to prevent abuse
    if top_k > 20:
        raise HTTPException(400, "top_k must be <= 20")
    
    # Sanitize query
    from somaai.utils.security import sanitize_query
    try:
        query = sanitize_query(query, max_length=500)
    except ValueError as e:
        raise HTTPException(400, str(e))
    
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
        
    # Build detailed response with comparison
    return {
        "query": query,
        "filters": {"grade": grade, "subject": subject},
        "reranker_available": reranker.is_available,
        "results": {
            "retrieval_count": len(raw_docs),
            "reranked_count": len(reranked_docs),
            "top_reranked": [
                {
                    "content": d.get("content", "")[:300],
                    "score": float(d.get("rerank_score", 0)),
                    "original_score": float(d.get("score", 0)),
                    "doc_id": d.get("metadata", {}).get("doc_id"),
                    "doc_title": d.get("metadata", {}).get("title", "Unknown"),
                    "page_start": d.get("metadata", {}).get("page_start", "?"),
                    "page_end": d.get("metadata", {}).get("page_end", "?"),
                    "rank": idx + 1,
                }
                for idx, d in enumerate(reranked_docs)
            ],
            "raw_top_5": [
                {
                    "content": d.get("content", "")[:300],
                    "score": float(d.get("score", 0)),
                    "doc_id": d.get("metadata", {}).get("doc_id"),
                    "doc_title": d.get("metadata", {}).get("title", "Unknown"),
                    "page_start": d.get("metadata", {}).get("page_start", "?"),
                    "page_end": d.get("metadata", {}).get("page_end", "?"),
                    "rank": idx + 1,
                }
                for idx, d in enumerate(raw_docs[:5])
            ],
        },
        "comparison": {
            "reranking_impact": "high" if reranker.is_available else "none",
            "score_improvement": _calculate_score_improvement(raw_docs, reranked_docs) if reranked_docs else 0,
        }
    }


def _calculate_score_improvement(raw_docs: list, reranked_docs: list) -> float:
    """Calculate average score improvement from reranking."""
    if not raw_docs or not reranked_docs:
        return 0.0
    
    raw_avg = sum(d.get("score", 0) for d in raw_docs[:5]) / min(5, len(raw_docs))
    reranked_avg = sum(d.get("rerank_score", 0) for d in reranked_docs[:5]) / min(5, len(reranked_docs))
    
    return float(reranked_avg - raw_avg)
