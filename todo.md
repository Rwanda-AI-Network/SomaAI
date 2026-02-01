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
  -F 'file=@uploads/Name of the document (ex: Computer Science S6 SB.pdf)' \
  -F 'grade=S6' \
  -F 'subject=name of the subject as in the db(ex: subjectcomputer_science)'

## Monitor the jobs
curl -X 'GET' \
  'http://localhost:8000/api/v1/ingest/jobs/"job id (ex: 635c83cc-57e9-4f81-b8e4-2afe38245167)' \
  -H 'accept: application/json'

or  "docker logs -f somaai-app"
