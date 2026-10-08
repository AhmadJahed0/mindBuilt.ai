"""Self-hosted Chroma client — deliberately not Chroma Cloud, so chunk
text and embeddings never leave infrastructure the client controls
(see architecture doc gap #2).

Section 3's "Design Decision" calls for Chroma collections as logical
workspace/security boundaries (personal / team / project / company-wide),
not one flat collection filtered by an ID list. Team and project
collections need DKK's real org structure to mean anything, so those wait.
What doesn't need DKK's input is the two-tier split every company has
regardless of org chart: a private collection per user, and one
company-wide shared collection. That's what's implemented here — team and
project collections can slot in later without reworking this.

COMPANY_SHARED_COLLECTION reuses the original "documents" collection name
(rather than renaming) so the corpus already embedded there doesn't need a
migration — it's the company-shared workspace now in every way that
matters except its physical Chroma name."""

import chromadb

from app.config import settings
from app.ingestion.embedder import embed_texts

_client = None
COMPANY_SHARED_COLLECTION = "documents"


def get_client():
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return _client


def personal_workspace_id(user_id: int) -> str:
    return f"personal_{user_id}"


def workspace_id_for(visibility: str, owner_user_id: int) -> str:
    """The single source of truth for which collection a document's chunks
    live in — used identically at ingest time, delete time, and query time
    so the three can never disagree about where a document's vectors are."""
    return personal_workspace_id(owner_user_id) if visibility == "private" else COMPANY_SHARED_COLLECTION


def get_collection(workspace_id: str = COMPANY_SHARED_COLLECTION):
    return get_client().get_or_create_collection(workspace_id)


def upsert_chunks(chunks: list[dict], workspace_id: str):
    """chunks: list of {text, document_id, filename, folder_id, folder_path,
    business_identifier, page_number, chunk_index}. folder_path and
    business_identifier are optional (Chroma metadata can't store None, so
    both fall back to "" rather than being omitted). workspace_id is stored
    on each chunk too (architecture doc Section 3.2) so it's visible in
    Chroma's own metadata, not just implied by which collection it's in."""
    collection = get_collection(workspace_id)
    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts)

    ids = [f"{c['document_id']}_{c['page_number']}_{c['chunk_index']}" for c in chunks]
    metadatas = [
        {
            "document_id": c["document_id"],
            "workspace_id": workspace_id,
            "filename": c["filename"],
            "folder_id": c["folder_id"] or 0,
            "folder_path": c.get("folder_path") or "",
            "business_identifier": c.get("business_identifier") or "",
            "page_number": c["page_number"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def delete_chunks_for_document(document_id: int, workspace_id: str):
    get_collection(workspace_id).delete(where={"document_id": document_id})


# Chroma returns the nearest neighbors it has regardless of whether they're
# actually relevant. Recalibrated against the real corpus (17 docs, several
# sharing "Standard Practice Memo" boilerplate): genuine matches scored
# 0.63-0.68 L2 distance; the first false positives (same-template, wrong
# document) started at 1.03; a fully irrelevant control question sat at
# 1.9+. 1.2 (picked when the corpus had 2 files) was already inside the
# false-positive zone. 0.95 sits in the gap with margin on both sides —
# recheck this if it starts either missing real matches or letting noise
# back in as the corpus keeps growing.
MAX_RELEVANT_DISTANCE = 0.95


def query_chunks(
    query: str,
    allowed_document_ids: list[int],
    workspace_ids: list[str],
    top_k: int = 20,
    apply_threshold: bool = True,
) -> list[dict]:
    """Vector search across every workspace collection the caller can see
    (their personal one plus company-shared), filtered to only the
    documents permissions.py says they're permitted to see. Querying an
    empty/nonexistent collection just returns no results, so no special
    case is needed for a user whose personal workspace is empty.

    allowed_document_ids must come from permissions.py — never trust a
    caller-supplied document scope without this filter applied.

    apply_threshold=False skips the relevance-distance filter — use this
    when allowed_document_ids has already been narrowed to one specific
    file or folder the caller explicitly chose. The threshold exists to
    separate relevant from irrelevant documents across a broad corpus
    search; once the caller has already picked the document, filtering
    its own chunks by "is this relevant enough" is the wrong question —
    caught by testing: a short query ("pipe size") scored 1.39 distance
    against the single correct, already-selected document and was
    silently dropped, even though it was obviously the right source."""
    if not allowed_document_ids:
        return []

    query_embedding = embed_texts([query])[0]

    chunks = []
    for workspace_id in workspace_ids:
        collection = get_collection(workspace_id)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"document_id": {"$in": allowed_document_ids}},
        )
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            if apply_threshold and distance > MAX_RELEVANT_DISTANCE:
                continue
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": distance,
            })
    return chunks
