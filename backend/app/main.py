import mimetypes
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import APIStatusError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Conversation, ChatMessage, Document, Folder, User
from app.ingestion.pipeline import save_and_ingest
from app.ingestion.folders import get_or_create_folder_path
from app.retrieval.vector_store import delete_chunks_for_document, workspace_id_for
from app.retrieval.permissions import resolve_accessible_document_ids
from app.storage import delete_file, read_file
from app.auth import hash_password, verify_password, create_token, get_current_user
from app.schemas import (
    SignupRequest,
    LoginRequest,
    AuthResponse,
    UserOut,
    ChatRequest,
    ChatResponse,
    UploadResponse,
    BatchUploadResult,
    DocumentOut,
    ConversationUpdate,
    ConversationOut,
    MessageOut,
)

app = FastAPI(title="mindbuilt.ai")

# Dev-only: allows the local Next.js frontend to call this API from the
# browser. Production should restrict this to the actual deployed frontend
# origin, not leave it wide open.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(token=create_token(user.id), user=user)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return AuthResponse(token=create_token(user.id), user=user)


@app.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.post("/documents/upload", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
    folder_id: int | None = Form(None),
    visibility: str = Form("shared"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stores the file, creates its SQL record, and runs it through the
    ingestion pipeline. Embedding requires an API key in .env — if none is
    configured, this will fail at the embedding step with a clear error,
    but parsing/chunking will have already succeeded."""
    if visibility not in ("shared", "private"):
        raise HTTPException(status_code=422, detail="visibility must be 'shared' or 'private'.")
    try:
        result = save_and_ingest(db, file, current_user.id, folder_id, visibility)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        # Embedding not configured yet — parsing still ran, so the file
        # and its SQL record exist; ingestion can be re-run once .env has a key.
        raise HTTPException(status_code=422, detail=str(e))
    except APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"Embedding provider error: {e.message}")

    return UploadResponse(**result)


@app.post("/documents/upload/batch", response_model=list[BatchUploadResult])
def upload_documents_batch(
    files: list[UploadFile] = File(...),
    paths: list[str] = Form(...),
    visibility: str = Form("shared"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk upload for a real archive — accepts many files at once, each with
    its relative path (e.g. "ProjectA/Drawings/site_plan.pdf") so the
    original folder structure gets recreated instead of flattening
    everything. One bad file (unsupported type, corrupt PDF, no embedding
    key) is reported per-file and does not abort the rest of the batch —
    that isolation matters once this is running against thousands of files."""
    if visibility not in ("shared", "private"):
        raise HTTPException(status_code=422, detail="visibility must be 'shared' or 'private'.")
    results = []
    for file, rel_path in zip(files, paths):
        folder_parts = rel_path.split("/")[:-1]
        try:
            folder_id = get_or_create_folder_path(db, folder_parts)
            outcome = save_and_ingest(db, file, current_user.id, folder_id, visibility)
            results.append(BatchUploadResult(
                filename=file.filename,
                path=rel_path,
                status="success",
                document_id=outcome["document_id"],
                chunk_count=outcome["chunk_count"],
            ))
        except Exception as e:
            db.rollback()
            results.append(BatchUploadResult(
                filename=file.filename,
                path=rel_path,
                status="error",
                error=str(e),
            ))
    return results


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every "shared" document, visible to any logged-in user, plus this
    user's own private ones — deliberately no finer-grained department/role
    filtering yet, that's Phase 2 work once DKK's real access rules are
    known. Reuses resolve_accessible_document_ids so this list always
    matches exactly what chat retrieval can actually see — a private
    document showing up here with nothing behind it (or vice versa) would
    make "private" a lie."""
    allowed_ids = resolve_accessible_document_ids(db, current_user.id)
    rows = db.execute(
        select(Document, Folder.path)
        .outerjoin(Folder, Document.folder_id == Folder.id)
        .where(Document.id.in_(allowed_ids))
        .order_by(Document.created_at.desc())
    ).all()

    return [
        DocumentOut(
            id=doc.id,
            filename=doc.filename,
            folder_path=folder_path,
            file_type=doc.file_type,
            processing_status=doc.processing_status,
            chunk_count=doc.chunk_count,
            visibility=doc.visibility,
            created_at=doc.created_at,
        )
        for doc, folder_path in rows
    ]


@app.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the original object-storage file, not the parsed/extracted
    text — retrieval and read_file always work off the parsed version, but
    the architecture doc is explicit that the original file stays available
    for "download/viewing and source verification": a user checking a
    citation should be able to see the real PDF/DOCX, not a text dump."""
    document = db.get(Document, document_id)
    if not document or document.id not in resolve_accessible_document_ids(db, current_user.id):
        raise HTTPException(status_code=404, detail="Document not found")

    content = read_file(document.storage_path)
    content_type = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Removes a document everywhere it lives: its vectors in Chroma, its
    file in storage, and its SQL row (which cascades to document_permissions).
    Vector/storage cleanup happens before the DB delete so a failure there
    leaves the document listed (and re-deletable) rather than silently
    orphaning chunks or a stored file with no owning row."""
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_chunks_for_document(document_id, workspace_id_for(document.visibility, document.owner_user_id))
    if document.storage_path:
        delete_file(document.storage_path)

    db.delete(document)
    db.commit()
    return {"deleted": document_id}


def _get_owned_conversation(db: Session, conversation_id: int, current_user: User) -> Conversation:
    """Fetches a conversation and checks the current user owns it — without
    this, any logged-in user could read, rename, pin, or delete anyone
    else's chat history just by guessing a conversation_id."""
    convo = db.get(Conversation, conversation_id)
    if not convo or convo.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@app.post("/conversations", response_model=ConversationOut)
def create_conversation(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    convo = Conversation(user_id=current_user.id, title="New chat")
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


@app.get("/conversations", response_model=list[ConversationOut])
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
    ).scalars().all()


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_conversation(db, conversation_id, current_user)
    msgs = db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc())
    ).scalars().all()
    return [
        MessageOut(role=m.role, content=m.content, citations=m.citations or [])
        for m in msgs
    ]


@app.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _get_owned_conversation(db, conversation_id, current_user)
    if payload.pinned is not None:
        convo.pinned = payload.pinned
    if payload.title is not None:
        convo.title = payload.title
    db.commit()
    db.refresh(convo)
    return convo


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = _get_owned_conversation(db, conversation_id, current_user)
    db.delete(convo)
    db.commit()
    return {"deleted": conversation_id}


@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.agent.graph import ask  # imported lazily so /health works with no LLM key set

    conversation = (
        _get_owned_conversation(db, req.conversation_id, current_user) if req.conversation_id else None
    )
    is_new = conversation is None
    if is_new:
        conversation = Conversation(user_id=current_user.id, title=req.question[:60])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    prior_messages = db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id.asc())
    ).scalars().all()
    history = [(m.role, m.content) for m in prior_messages]

    db.add(ChatMessage(conversation_id=conversation.id, role="user", content=req.question))
    db.commit()

    try:
        answer, citations = ask(db, current_user.id, req.question, history=history)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except APIStatusError as e:
        # Surfaces the provider's own message (e.g. insufficient quota,
        # invalid key) instead of a generic 500.
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e.message}")

    db.add(ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations=[c for c in citations],
    ))
    if not is_new and conversation.title == "New chat":
        conversation.title = req.question[:60]
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    return ChatResponse(answer=answer, citations=citations, conversation_id=conversation.id)
