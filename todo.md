Todo:::::
5. Refactor the models to SQLAlchemy 2.0 style (Option 2), which provides:
    - Better type safety
    - Better IDE autocomplete
    - No need for casts

7. Analogies are not being shown and passed in the response.

## To run the ingestion on the command line
curl -X 'POST' \
  'http://localhost:8000/api/v1/ingest' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@uploads/Computer Science S6 SB.pdf' \
  -F 'grade=S6' \
  -F 'subject=computer_science'

## Monitor the jobs
curl -X 'GET' \
  'http://localhost:8000/api/v1/ingest/jobs/"job id (ex: 635c83cc-57e9-4f81-b8e4-2afe38245167)' \
  -H 'accept: application/json'

or  "docker logs -f somaai-app"





Step 2 to go with:::

Query Classification — Add a lightweight classifier before the RAG pipeline to detect greetings/chit-chat and skip retrieval entirely. Right now, even a "hi" triggers the full pipeline (embed → Qdrant search → LLM generation). This wastes latency and API calls. The idea was a simple regex or small model check: "Is this a question about curriculum content?" → Yes: run RAG. No: respond directly.

Retrieval Evaluation Framework — Build a small ground-truth dataset of ~20-30 

(question, expected_page/chunk)
 pairs from your actual curriculum PDFs, then compute Recall@K and MRR (Mean Reciprocal Rank). This was flagged as the single most impactful missing piece because without it, every retrieval "improvement" is a guess. You can't know if switching embedding models or tuning chunk sizes actually helps.

Metadata Normalization — Fix the grade="S6" vs grade="s6" mismatch that silently kills retrieval. Normalize to lowercase at both ingestion and query time.

SSE Streaming — Add Server-Sent Events for the chat endpoint so students don't stare at a blank screen for 10+ seconds while the pipeline runs.

Groq JSON Mode — Switch from hoping the LLM returns valid JSON to using Groq's response_format={"type": "json_object"} for guaranteed valid JSON, eliminating the fragile fallback parsing.

