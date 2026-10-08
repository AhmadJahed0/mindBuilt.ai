from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, UniqueConstraint, Boolean, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db import Base


class PermissionLevel(str, enum.Enum):
    read = "read"
    write = "write"
    manage = "manage"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    users = relationship("User", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))

    department = relationship("Department", back_populates="users")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True)
    parent_folder_id = Column(Integer, ForeignKey("folders.id"))
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)

    documents = relationship("Document", back_populates="folder")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    folder_id = Column(Integer, ForeignKey("folders.id"))
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"))
    owner_department_id = Column(Integer, ForeignKey("departments.id"))
    file_type = Column(String, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    processing_status = Column(String, nullable=False, default="pending")
    chunk_count = Column(Integer, nullable=False, default=0)
    visibility = Column(String, nullable=False, default="shared")  # "shared" | "private" — which Chroma workspace it's embedded in
    content_hash = Column(String)  # sha256 of the raw file bytes, for canonical-document dedup (architecture doc Section 3.1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    folder = relationship("Folder", back_populates="documents")
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan")


class DocumentPermission(Base):
    __tablename__ = "document_permissions"
    __table_args__ = (UniqueConstraint("document_id", "user_id"),)

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    permission = Column(Enum(PermissionLevel), nullable=False)

    document = relationship("Document", back_populates="permissions")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False, default="New chat")
    pinned = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"))
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    citations = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
