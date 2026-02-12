import asyncio
import logging
from somaai.modules.knowledge.stores.qdrant import QdrantStore
from somaai.settings import settings
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

logging.basicConfig(level=logging.INFO)

async def main():
    store = QdrantStore(settings)
    
    # latest doc id from logs
    target_doc_id = "b7f42226-c983-4d92-bccb-dc4e72b5e14d"
    
    print(f"Inspecting chunks for doc_id: {target_doc_id}")
    
    try:
        # Search by doc_id directly
        client = store.client
        
        # Scroll to get chunks
        results, next_page = client.scroll(
            collection_name="somaai_documents",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.doc_id",
                        match=MatchValue(value=target_doc_id)
                    )
                ]
            ),
            limit=10,
            with_payload=True
        )
        
        print(f"Found {len(results)} chunks.")
        
        for i, point in enumerate(results):
            payload = point.payload
            content = payload.get("content", "")
            meta = payload.get("metadata", {})
            page = meta.get("page_start", "?")
            
            print(f"\n--- Chunk {i+1} (Page {page}) ---")
            print(f"Content Preview (first 200 chars):\n{content[:200]}")
            print(f"Content Preview (middle 100 chars):\n{content[len(content)//2 : len(content)//2 + 100]}")
            
            # Run garbage check on this chunk
            from somaai.modules.ingest.quality import is_garbage_text
            is_garbage = is_garbage_text(content)
            print(f"Garbage Detection Result: {is_garbage}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
