from datetime import datetime

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class ChatRequest(BaseModel):
    question: str
    conversation_id: int | None = None


class Citation(BaseModel):
    document_id: int
    filename: str
    page_number: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    conversation_id: int


class UploadResponse(BaseModel):
    document_id: int
    filename: str
    chunk_count: int
    processing_status: str


class BatchUploadResult(BaseModel):
    filename: str
    path: str
    status: str  # "success" | "error"
    document_id: int | None = None
    chunk_count: int | None = None
    error: str | None = None


class DocumentOut(BaseModel):
    id: int
    filename: str
    folder_path: str | None
    file_type: str
    processing_status: str
    visibility: str
    chunk_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationUpdate(BaseModel):
    pinned: bool | None = None
    title: str | None = None


class ConversationOut(BaseModel):
    id: int
    title: str
    pinned: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    role: str
    content: str
    citations: list[Citation] = []

    class Config:
        from_attributes = True
