# Coreveil

Private, internal knowledge assistant — a RAG system over a company's own
documents, with SQL-enforced permissions and no data sent anywhere outside
infrastructure the client controls. Built from the architecture doc for
the DKK engagement; designed to be reused for future clients.

## What's runnable right now, with zero API keys

- The full SQL schema (`db/init.sql`) — departments, users, folders,
  documents, document_permissions.
- The ingestion pipeline's parsing and chunking stages (PDF via PyMuPDF,
  DOCX, XLSX, TXT/MD, OCR fallback via Tesseract, token-aware chunking).
- The permission-resolution logic (`app/retrieval/permissions.py`) —
  testable against fake users and fake documents.
- The four retrieval tools (`app/retrieval/tools.py`), permission-filtered.
- The chat UI shell (frontend).

Two sample text files are in `backend/sample_docs/` for testing ingestion
without needing any of DKK's real documents.

## What needs an API key

Generating embeddings and running the chat agent both need an LLM
provider. Copy `.env.example` to `.env` and fill in **one** provider
(OpenAI, Azure OpenAI, or Anthropic). Until that's set, `/documents/upload`
will parse and chunk successfully, then fail clearly at the embedding
step — that failure is expected and not a bug.

Production should use Azure OpenAI inside the client's own Azure tenant
(see architecture doc, Section 5) — this `.env` setup is for local dev only.

## Running it

```bash
cp .env.example .env   # then edit in your API key
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/health
- Chroma: http://localhost:8001

Upload a sample doc to test the pipeline:

```bash
curl -F "file=@backend/sample_docs/rfi_process.txt" \
     -F "owner_user_id=1" \
     http://localhost:8000/documents/upload
```

You'll need at least one row in `users` first — connect to the `postgres`
container and insert one, or add a seed script once this is further along.

## Open architecture decisions (from the doc review)

1. **Embeddings must go through the same Azure deployment as chat**, not
   the public OpenAI API — otherwise the privacy story has a quiet leak.
   `app/ingestion/embedder.py` supports both; production should be forced
   to `azure`.
2. **Chroma is self-hosted here on purpose**, not Chroma Cloud, so vectors
   never leave infrastructure the client controls.
3. **No deletion/retention workflow yet.** When a document is removed from
   the source, its chunks in Chroma and its file in storage need to be
   cascade-deleted. Not built yet — flag before this goes to production.

## Blocked on DKK's Phase 0 answers

- Real ingestion volume and OCR percentage (their actual archive)
- Cloud vs. more locked-down hosting (their compliance/government-contract status)
- Real department/role structure (maps directly onto `departments` and
  `document_permissions`)
- Their SSO provider, to replace the hardcoded `user_id` in the frontend
  with real authentication
