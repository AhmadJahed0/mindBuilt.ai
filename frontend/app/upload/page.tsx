"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authFetch, getToken, downloadDocument } from "../lib/auth";

type FileRow = {
  file: File;
  path: string;
  status: "pending" | "uploading" | "success" | "error";
  chunkCount?: number;
  error?: string;
};

type LibraryDoc = {
  id: number;
  filename: string;
  folder_path: string | null;
  file_type: string;
  processing_status: string;
  chunk_count: number;
  visibility: "shared" | "private";
  created_at: string;
};

export default function UploadPage() {
  const router = useRouter();
  const [rows, setRows] = useState<FileRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [visibility, setVisibility] = useState<"shared" | "private">("shared");
  const [library, setLibrary] = useState<LibraryDoc[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const filesInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    refreshLibrary();
  }, [router]);

  async function refreshLibrary() {
    setLibraryLoading(true);
    try {
      const res = await authFetch(`/documents`);
      if (res.ok) setLibrary(await res.json());
    } catch {
      // Library staying stale on a network hiccup isn't worth an error banner.
    } finally {
      setLibraryLoading(false);
    }
  }

  function addFiles(fileList: FileList | null) {
    if (!fileList) return;
    const next: FileRow[] = Array.from(fileList).map((file) => ({
      file,
      // webkitRelativePath is set automatically for a folder picker; for a
      // plain multi-file select or drag-drop it falls back to a flat name.
      path: (file as any).webkitRelativePath || file.name,
      status: "pending",
    }));
    setRows((prev) => [...prev, ...next]);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  }

  function clearAll() {
    setRows([]);
  }

  async function uploadAll() {
    const pending = rows.filter((r) => r.status === "pending" || r.status === "error");
    if (pending.length === 0 || uploading) return;
    setUploading(true);
    setRows((prev) => prev.map((r) => (pending.includes(r) ? { ...r, status: "uploading" } : r)));

    const formData = new FormData();
    pending.forEach((r) => formData.append("files", r.file));
    pending.forEach((r) => formData.append("paths", r.path));
    formData.append("visibility", visibility);

    try {
      const res = await authFetch(`/documents/upload/batch`, { method: "POST", body: formData });
      const results = await res.json();

      setRows((prev) =>
        prev.map((r) => {
          const match = results.find((x: any) => x.path === r.path && x.filename === r.file.name);
          if (!match) return r;
          return match.status === "success"
            ? { ...r, status: "success", chunkCount: match.chunk_count }
            : { ...r, status: "error", error: match.error };
        })
      );
    } catch {
      setRows((prev) =>
        prev.map((r) => (pending.includes(r) ? { ...r, status: "error", error: "Couldn't reach the backend." } : r))
      );
    } finally {
      setUploading(false);
      refreshLibrary();
    }
  }

  async function handleDownload(doc: LibraryDoc) {
    setDownloadingId(doc.id);
    try {
      await downloadDocument(doc.id, doc.filename);
    } finally {
      setDownloadingId(null);
    }
  }

  async function deleteDocument(doc: LibraryDoc) {
    if (!window.confirm(`Delete "${doc.filename}"? This removes it from the index and cannot be undone.`)) return;
    setDeletingId(doc.id);
    try {
      const res = await authFetch(`/documents/${doc.id}`, { method: "DELETE" });
      if (res.ok) {
        setLibrary((prev) => prev.filter((d) => d.id !== doc.id));
      }
    } catch {
      // Leaving the row in place on a network failure is more honest than
      // pretending the delete succeeded.
    } finally {
      setDeletingId(null);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  const pendingCount = rows.filter((r) => r.status === "pending" || r.status === "error").length;

  return (
    <div className="upload-page">
      <Link href="/" className="nav-link" style={{ marginLeft: 0, marginBottom: 18, display: "inline-flex" }}>
        ← Back to chat
      </Link>

      <h1>Upload Documents</h1>
      <p className="sub">
        Pick a folder to preserve its structure, or select individual files. Supported types: .txt, .md, .pdf, .docx, .xlsx —
        scanned pages inside PDFs are OCR'd automatically.
      </p>

      <div
        className={`dropzone ${dragOver ? "active" : ""}`}
        onClick={() => filesInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <div className="dropzone-icon">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7 18a4.5 4.5 0 0 1-1-8.9A5.5 5.5 0 0 1 16.9 7 4.5 4.5 0 0 1 17 18H7Z" />
            <path d="M12 12v7M9.5 14.5 12 12l2.5 2.5" />
          </svg>
        </div>
        <strong>Click to choose files, or drop them here</strong>
        Use "Choose folder" below instead if you want to preserve a folder's structure.

        <div className="upload-actions" onClick={(e) => e.stopPropagation()}>
          <button className="pill-btn" onClick={() => folderInputRef.current?.click()}>
            Choose folder
          </button>
          <button className="pill-btn" onClick={() => filesInputRef.current?.click()}>
            Choose files
          </button>
        </div>

        {/* @ts-ignore — webkitdirectory isn't in the standard TS DOM types */}
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          hidden
          onChange={(e) => addFiles(e.target.files)}
        />
        <input ref={filesInputRef} type="file" multiple hidden onChange={(e) => addFiles(e.target.files)} />
      </div>

      {rows.length > 0 && (
        <>
          <div className="visibility-toggle">
            <span>Who can see these files?</span>
            <div className="visibility-options">
              <button
                type="button"
                className={visibility === "shared" ? "active" : ""}
                onClick={() => setVisibility("shared")}
                disabled={uploading}
              >
                Shared with everyone
              </button>
              <button
                type="button"
                className={visibility === "private" ? "active" : ""}
                onClick={() => setVisibility("private")}
                disabled={uploading}
              >
                Private to me
              </button>
            </div>
          </div>

          <div className="upload-actions">
            <button className="pill-btn primary" onClick={uploadAll} disabled={pendingCount === 0 || uploading}>
              {uploading ? "Uploading..." : `Upload ${pendingCount || ""} file${pendingCount === 1 ? "" : "s"}`}
            </button>
            <button className="pill-btn" onClick={clearAll} disabled={uploading}>
              Clear list
            </button>
          </div>

          <div className="file-table">
            {rows.map((r, i) => (
              <div className="file-row" key={i}>
                <span className="path">{r.path}</span>
                {r.status === "error" && r.error && <span className="error-msg">{r.error}</span>}
                {r.status === "success" && (
                  <span style={{ fontSize: 11.5, color: "var(--ink-soft)" }}>{r.chunkCount} chunk(s)</span>
                )}
                <span className={`status-pill ${r.status}`}>{r.status}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="library">
        <div className="library-header">
          <h2>Document Library</h2>
          <span className="library-count">
            {libraryLoading ? "loading..." : `${library.length} document${library.length === 1 ? "" : "s"}`}
          </span>
        </div>

        {!libraryLoading && library.length === 0 && (
          <div className="library-empty">Nothing uploaded yet — everything you add shows up here.</div>
        )}

        {library.length > 0 && (
          <div className="library-table">
            {library.map((d) => (
              <div className="doc-row" key={d.id}>
                <span className="filename">{d.filename}</span>
                {d.visibility === "private" && <span className="visibility-badge">Private</span>}
                {d.folder_path && <span className="folder">{d.folder_path}</span>}
                <span className="meta">{d.chunk_count} chunk(s)</span>
                <span className="meta">{formatDate(d.created_at)}</span>
                <span className={`status-pill ${d.processing_status === "processed" ? "success" : "error"}`}>
                  {d.processing_status}
                </span>
                <button
                  className="icon-btn"
                  title={`Download ${d.filename}`}
                  onClick={() => handleDownload(d)}
                  disabled={downloadingId === d.id}
                >
                  {downloadingId === d.id ? (
                    "…"
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
                    </svg>
                  )}
                </button>
                <button
                  className="icon-btn danger"
                  title={`Delete ${d.filename}`}
                  onClick={() => deleteDocument(d)}
                  disabled={deletingId === d.id}
                >
                  {deletingId === d.id ? (
                    "…"
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
                    </svg>
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
