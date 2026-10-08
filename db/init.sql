-- Coreveil: core schema
-- Matches the permissions model from the architecture doc:
-- ownership and access are separate; SQL is the source of truth for both.

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id)
);

CREATE TABLE folders (
    id SERIAL PRIMARY KEY,
    parent_folder_id INTEGER REFERENCES folders(id),
    name TEXT NOT NULL,
    path TEXT NOT NULL
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    folder_id INTEGER REFERENCES folders(id),
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    owner_user_id INTEGER REFERENCES users(id),
    owner_department_id INTEGER REFERENCES departments(id),
    file_type TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id),
    processing_status TEXT NOT NULL DEFAULT 'pending',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    visibility TEXT NOT NULL DEFAULT 'shared',
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_content_hash ON documents(content_hash);

CREATE TYPE permission_level AS ENUM ('read', 'write', 'manage');

CREATE TABLE document_permissions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    permission permission_level NOT NULL,
    UNIQUE (document_id, user_id)
);

CREATE INDEX idx_documents_folder ON documents(folder_id);
CREATE INDEX idx_permissions_user ON document_permissions(user_id);
CREATE INDEX idx_permissions_document ON document_permissions(document_id);

-- Chat history: sidebar conversations + their messages.
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL DEFAULT 'New chat',
    pinned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_messages_conversation ON chat_messages(conversation_id);
