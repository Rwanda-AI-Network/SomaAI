## To run the ingestion on the command line
curl -X 'POST' \
  'http://localhost:8000/api/v1/ingest' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@uploads/Computer Science S6 SB.pdf' \
  -F 'grade=S6' \
  -F 'subject=computer_science'

## Monitor the jobs
"docker logs -f somaai-app"




Todo:::::
==== Evaluation ===
- Build a small ground-truth dataset of ~20-30 (question, expected_page/chunk) pairs from your actual curriculum PDFs, then compute Recall@K and MRR (Mean Reciprocal Rank). This was flagged as the single most impactful missing piece because without it, every retrieval "improvement" is a guess. You can't know if switching embedding models or tuning chunk sizes actually helps.
==== Metadata Normalization ===
- Metadata Normalization — Fix the grade="S6" vs grade="s6" mismatch that silently kills retrieval. Normalize to lowercase at both ingestion and query time.
==== SSE Streaming ===
- SSE Streaming — Add Server-Sent Events for the chat endpoint so students don't stare at a blank screen for 10+ seconds while the pipeline runs.
==== Groq JSON Mode ===
- Groq JSON Mode — Switch from hoping the LLM returns valid JSON to using Groq's response_format={"type": "json_object"} for guaranteed valid JSON, eliminating the fragile fallback parsing.

==== Prompt Engineering ===
- Teacher and analogies ::: prompt engineering to get the text layout
- Citations being showin in the chat :::  should be removed from the chat response

