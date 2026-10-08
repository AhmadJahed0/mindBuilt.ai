"""The four file-oriented tools handed to the ReAct agent (Section 4.1 of
the architecture doc). The agent never touches Chroma, SQL, or storage
directly — every tool call here resolves permissions first.
"""

import re
from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Document, Folder
from app.retrieval.permissions import resolve_accessible_document_ids, resolve_workspace_ids_for_user
from app.retrieval.vector_store import query_chunks
from app.retrieval.decompose import decompose_query
from app.retrieval.rerank import rerank_chunks
from app.ingestion.pipeline import extract_pages


def search_files_tool(db: Session, user_id: int, query: str) -> list[dict]:
    """Locate files by filename or business identifier (e.g. a project code).

    Matches the folder path as well as the filename: a project code is
    often encoded in the folder structure (e.g. "Projects/AB31/report.txt")
    rather than repeated in every filename inside it. Caught by testing: a
    folder-organized batch upload was invisible to "what documents do we
    have for project AB31" when this only matched Document.filename.

    Matches on individual words, not the whole query as one substring.
    The agent frequently passes a natural-language phrase ("AB31 drainage
    project") rather than a single keyword — matching that whole phrase
    verbatim misses an obvious match like a folder literally named AB31,
    since "AB31 drainage project" never appears as one substring anywhere.
    Caught by testing: this exact phrasing returned zero results even
    though "Projects/AB31" plainly should have matched, which then sent
    the agent down a path of guessing folder_ids that don't exist."""
    allowed_ids = resolve_accessible_document_ids(db, user_id)
    if not allowed_ids:
        return []

    words = [w for w in re.findall(r"[A-Za-z0-9]+", query) if len(w) >= 3] or [query]
    word_conditions = [
        (Document.filename.ilike(f"%{w}%")) | (Folder.path.ilike(f"%{w}%"))
        for w in words
    ]

    matches = db.execute(
        select(Document)
        .outerjoin(Folder, Document.folder_id == Folder.id)
        .where(Document.id.in_(allowed_ids), or_(*word_conditions))
    ).scalars().all()

    return [{"document_id": d.id, "filename": d.filename, "folder_id": d.folder_id} for d in matches]


def list_folder_tool(db: Session, user_id: int, folder_id: int) -> list[dict]:
    """List documents inside a folder the user is allowed to see."""
    allowed_ids = set(resolve_accessible_document_ids(db, user_id))

    docs = db.execute(
        select(Document).where(Document.folder_id == folder_id)
    ).scalars().all()

    return [
        {"document_id": d.id, "filename": d.filename}
        for d in docs
        if d.id in allowed_ids
    ]


# A dominant document needs at least this many chunks in the candidate set,
# and to account for at least this fraction of them, before it's worth a
# second, more targeted retrieval scoped to just that document (architecture
# doc Section 4.3, steps 6-7). Picked to trigger only on a genuine cluster —
# e.g. 3 of 4 candidate chunks from one file — not on two chunks that just
# happen to share a document out of a dozen unrelated ones.
CLUSTER_MIN_CHUNKS = 3
CLUSTER_MIN_FRACTION = 0.5


def _dominant_document_id(chunks: list[dict]) -> int | None:
    if len(chunks) < CLUSTER_MIN_CHUNKS:
        return None
    counts = Counter(c["metadata"]["document_id"] for c in chunks)
    doc_id, count = counts.most_common(1)[0]
    return doc_id if count / len(chunks) >= CLUSTER_MIN_FRACTION else None


def query_documents_tool(
    db: Session,
    user_id: int,
    query: str,
    mode: str = "auto",
    file_id: int | None = None,
    folder_id: int | None = None,
) -> list[dict]:
    """Primary RAG retrieval tool. mode='file' scopes to one document_id,
    mode='folder' scopes to everything inside one folder_id, mode='auto'
    (default) searches everything the user can access.

    'auto' mode searches with the original question AND its decomposed
    sub-parts, then merges. The original alone sometimes already covers a
    multi-topic question fine (its embedding can land close to multiple
    relevant chunks); decomposition exists as a safety net for the cases
    where it doesn't. Relying on decomposition ALONE was tried and made
    things worse: an LLM-paraphrased sub-query ("Who founded DKK?" instead
    of "Who founded DKK Consulting?") scored measurably worse than either
    the original phrasing or a more careful decomposition — so this
    layers both rather than trusting either one alone.

    Vector Search -> Merge Results -> detect a dominant document -> a second
    scoped retrieval against it if one stands out -> Rerank, per the
    architecture doc's retrieval pipeline (Section 4.3)."""
    allowed_ids = resolve_accessible_document_ids(db, user_id)
    workspace_ids = resolve_workspace_ids_for_user(user_id)

    if mode == "file" and file_id is not None:
        if file_id not in allowed_ids:
            return []  # never search a document outside the permission set
        results = query_chunks(
            query, allowed_document_ids=[file_id], workspace_ids=workspace_ids, apply_threshold=False
        )
        return rerank_chunks(query, results)

    if mode == "folder" and folder_id is not None:
        folder_document_ids = set(
            db.execute(select(Document.id).where(Document.folder_id == folder_id)).scalars().all()
        )
        scoped_ids = [d for d in allowed_ids if d in folder_document_ids]
        if not scoped_ids:
            return []
        results = query_chunks(
            query, allowed_document_ids=scoped_ids, workspace_ids=workspace_ids, apply_threshold=False
        )
        return rerank_chunks(query, results)

    sub_queries = [query] + [q for q in decompose_query(query) if q != query]
    seen = set()
    merged: list[dict] = []
    for sub_query in sub_queries:
        for chunk in query_chunks(sub_query, allowed_document_ids=allowed_ids, workspace_ids=workspace_ids):
            meta = chunk["metadata"]
            key = (meta["document_id"], meta["page_number"], meta["chunk_index"])
            if key not in seen:
                seen.add(key)
                merged.append(chunk)

    # If the candidates strongly cluster around one document, that document
    # is clearly the answer's real home — pull more of it in with a second,
    # scoped retrieval rather than leaving the answer to whatever fraction
    # of it happened to make the first, broader top_k cut.
    dominant_id = _dominant_document_id(merged)
    if dominant_id is not None:
        for chunk in query_chunks(
            query, allowed_document_ids=[dominant_id], workspace_ids=workspace_ids, top_k=10, apply_threshold=False
        ):
            meta = chunk["metadata"]
            key = (meta["document_id"], meta["page_number"], meta["chunk_index"])
            if key not in seen:
                seen.add(key)
                merged.append(chunk)

    return rerank_chunks(query, merged)


# Reading an entire large document unconditionally risks blowing the LLM's
# context window (and the API bill) on a single tool call. Anything within
# this many pages is short enough to just read whole — matches the
# architecture doc's "inspect a short complete document" case.
MAX_PAGES_WITHOUT_RANGE = 15


def read_file_tool(
    db: Session,
    user_id: int,
    document_id: int,
    start_page: int | None = None,
    end_page: int | None = None,
) -> str:
    """Reads a document's extracted text, for when top-ranked chunks aren't
    enough context. Still gated by permission resolution. Without a page
    range, large documents are truncated rather than dumped whole into the
    LLM's context (architecture doc Section 4.1) — the truncation note
    tells the agent how to ask for the rest."""
    allowed_ids = resolve_accessible_document_ids(db, user_id)
    if document_id not in allowed_ids:
        return ""

    document = db.get(Document, document_id)
    if not document:
        return ""

    pages = extract_pages(document.storage_path)
    total = len(pages)

    if start_page is not None or end_page is not None:
        start = max(1, start_page or 1)
        end = min(total, end_page or total)
        selected = pages[start - 1:end]
    elif total > MAX_PAGES_WITHOUT_RANGE:
        selected = pages[:MAX_PAGES_WITHOUT_RANGE]
    else:
        selected = pages

    text = "\n\n".join(p["text"] for p in selected if p.get("text"))

    if len(selected) < total and start_page is None and end_page is None:
        text += (
            f"\n\n[Showing pages 1-{MAX_PAGES_WITHOUT_RANGE} of {total}. Call read_file again with "
            "start_page/end_page to see more of this document.]"
        )

    return text
