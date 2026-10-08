import hashlib
import os
import tempfile

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Folder
from app.storage import save_file, read_file
from app.ingestion.chunker import chunk_text
from app.ingestion.parsers.text_parser import parse_text
from app.ingestion.parsers.pdf_parser import parse_pdf, render_page_image
from app.ingestion.parsers.docx_parser import parse_docx
from app.ingestion.parsers.xlsx_parser import parse_xlsx
from app.ingestion.parsers.ocr import ocr_page_image
from app.ingestion.business_identifier import extract_business_identifier
from app.ingestion.clean import clean_text
from app.retrieval.vector_store import upsert_chunks, workspace_id_for

PARSERS = {
    ".txt": parse_text,
    ".md": parse_text,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".xlsx": parse_xlsx,
}


def extract_pages(storage_path: str) -> list[dict]:
    """Detects file type, routes to the right parser, and applies OCR
    fallback for PDF pages that came back with no native text.

    Parsers (PyMuPDF, python-docx, openpyxl) all expect a local file path.
    For a local storage_path that's already true; for a remote one
    (supabase://...) the file is downloaded to a temp path first so the
    parsing code below never has to know which storage provider is active."""
    ext = os.path.splitext(storage_path)[1].lower()
    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(f"No parser registered for file type: {ext}")

    is_remote = "://" in storage_path
    local_path = storage_path
    tmp = None
    if is_remote:
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(read_file(storage_path))
        tmp.close()
        local_path = tmp.name

    try:
        pages = parser(local_path)

        if ext == ".pdf":
            for page in pages:
                if page.get("needs_ocr"):
                    pixmap = render_page_image(local_path, page["page"])
                    page["text"] = ocr_page_image(pixmap)

        return pages
    finally:
        if tmp:
            os.unlink(tmp.name)


def ingest_document(db: Session, document: Document, embed: bool = True) -> int:
    """Runs the full pipeline for one already-recorded document: extract,
    clean, chunk, embed, and store in Chroma. Returns the chunk count.

    Set embed=False to test parsing/chunking without an API key configured.
    """
    pages = extract_pages(document.storage_path)

    folder_path = None
    if document.folder_id:
        folder = db.get(Folder, document.folder_id)
        folder_path = folder.path if folder else None

    business_identifier = extract_business_identifier(document.filename, folder_path)

    all_chunks = []
    for page in pages:
        text = clean_text(page["text"] or "")
        if not text:
            continue
        for chunk_index, chunk in enumerate(chunk_text(text)):
            all_chunks.append({
                "text": chunk,
                "document_id": document.id,
                "filename": document.filename,
                "folder_id": document.folder_id,
                "folder_path": folder_path,
                "business_identifier": business_identifier,
                "page_number": str(page["page"]),
                "chunk_index": chunk_index,
            })

    if embed and all_chunks:
        workspace_id = workspace_id_for(document.visibility, document.owner_user_id)
        upsert_chunks(all_chunks, workspace_id)

    document.chunk_count = len(all_chunks)
    document.processing_status = "processed" if all_chunks else "empty"
    db.commit()

    return len(all_chunks)


def save_and_ingest(
    db: Session,
    file: UploadFile,
    owner_user_id: int | None,
    folder_id: int | None,
    visibility: str = "shared",
) -> dict:
    """Shared by the single-file and batch upload endpoints. Storage
    filenames are namespaced by document id — two different files named
    report.pdf in two different folders must not silently overwrite each
    other on disk, which the original filename-only path allowed."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in PARSERS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(PARSERS)}. "
            "Scanned drawings and CAD files (.dwg) need a converter step before "
            "they can go through this pipeline — not handled yet."
        )

    content = file.file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    # Canonical Document Rule (architecture doc Section 3.1): a document is
    # stored and embedded once. Scoped to "shared" docs plus this uploader's
    # own docs, not a company-wide hash lookup — matching against a
    # stranger's private document would leak "this exact file exists" to
    # someone who can't see it.
    existing = db.execute(
        select(Document).where(
            Document.content_hash == content_hash,
            (Document.visibility == "shared") | (Document.owner_user_id == owner_user_id),
        )
    ).scalar_one_or_none()
    if existing:
        raise ValueError(
            f"This exact file already exists as \"{existing.filename}\" (document #{existing.id}) — "
            "not re-uploading a duplicate copy."
        )

    document = Document(
        folder_id=folder_id,
        filename=file.filename,
        storage_path="",  # set below once we have the document id
        owner_user_id=owner_user_id,
        file_type=ext,
        uploaded_by=owner_user_id,
        visibility=visibility,
        content_hash=content_hash,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    key = f"{document.id}_{file.filename}"
    document.storage_path = save_file(key, content)
    db.commit()

    chunk_count = ingest_document(db, document)

    return {
        "document_id": document.id,
        "filename": document.filename,
        "chunk_count": chunk_count,
        "processing_status": document.processing_status,
    }
