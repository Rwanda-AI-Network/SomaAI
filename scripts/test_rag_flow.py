import asyncio
import os
import sys
import httpx
import time

BASE_URL = "http://localhost:8000/api/v1"

async def run_test():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("1. Checking API Health...")
        try:
            resp = await client.get("http://localhost:8000/health")
            resp.raise_for_status()
            print("âœ… API is healthy")
        except Exception as e:
            print(f"âŒ API is not reachable: {e}")
            sys.exit(1)

        # 2. Upload Document
        print("\n2. Uploading Document...")
        file_path = "test_document.txt"
        if not os.path.exists(file_path):
            print(f"âŒ Dictionary {file_path} not found!")
            sys.exit(1)

        with open(file_path, "rb") as f:
            files = {"file": ("test_document.txt", f, "text/plain")}
            data = {
                "grade": "S1", 
                "subject": "social_studies", 
                "title": "Rwanda Vision 2050 Test"
            }
            resp = await client.post(f"{BASE_URL}/ingest", files=files, data=data)
        
        if resp.status_code != 200:
            print(f"âŒ Upload failed: {resp.text}")
            sys.exit(1)
            
        print("âœ… Upload successful")
        job_id = resp.json()["job_id"]
        doc_id = resp.json()["doc_id"]
        print(f"   Job ID: {job_id}")
        print(f"   Doc ID: {doc_id}")

        # 3. Poll Job Status
        print("\n3. Waiting for Ingestion...")
        while True:
            resp = await client.get(f"{BASE_URL}/ingest/jobs/{job_id}")
            job = resp.json()
            status = job["status"]
            print(f"   Status: {status}")
            
            if status == "completed":
                print("âœ… Ingestion Complete")
                break
            elif status == "failed":
                print(f"âŒ Ingestion Failed: {job.get('error')}")
                # We continue anyway to see if chat works (maybe partial success?)
                break
            
            await asyncio.sleep(2)

        # 4. Test Chat
        print("\n4. Testing Chat Retrieval...")
        chat_payload = {
            "question": "What are the pillars of Vision 2050?",
            "grade": "S1",
            "subject": "social_studies",
            "user_role": "student",
            "session_id": "test-session-1"
        }
        # Anonymous header
        headers = {"X-Actor-Id": "test-user-1"} 
        
        resp = await client.post(f"{BASE_URL}/chat/ask", json=chat_payload, headers=headers)
        
        if resp.status_code not in (200, 201):
            print(f"âŒ Chat failed: {resp.text}")
            sys.exit(1)
            
        result = resp.json()
        print("âœ… Chat Response Received")
        print(f"   Answer: {result['answer'][:100]}...")
        
        citations = result.get("citations", [])
        print(f"   Citations Found: {len(citations)}")
        for cit in citations:
            print(f"   - [{cit.get('doc_title')}] Page {cit.get('page_number')}: {cit.get('quote')}")

        if citations:
            print("\nâœ¨ SUCCESS: Citations were retrieved from the uploaded document!")
        else:
            print("\nâš ï¸ WARNING: No citations found. Retrieval might have failed or mock fallback was used.")

if __name__ == "__main__":
    asyncio.run(run_test())
