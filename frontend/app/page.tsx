"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { authFetch, getToken, getStoredUser, clearSession, downloadDocument, AuthUser } from "./lib/auth";

type Citation = { document_id: number; filename: string; page_number: string };
type Message = { role: "user" | "assistant"; text: string; citations?: Citation[]; error?: boolean };
type Conversation = { id: number; title: string; pinned: boolean; updated_at: string };

const SUGGESTIONS = [
  "Who has to approve an RFI over $5,000?",
  "What's the minimum width for a drainage easement?",
  "Who's our standard geotechnical vendor?",
];

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const threadEndRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Redirect to login before rendering anything that would call the API —
  // a stale/expired token still triggers a redirect later via authFetch's
  // own 401 handling, this just avoids the flash of an empty chat first.
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setUser(getStoredUser());
  }, [router]);

  function logout() {
    clearSession();
    router.replace("/login");
  }

  // Sidebar open/closed is a per-viewer convenience, not shared state.
  useEffect(() => {
    const stored = localStorage.getItem("coreveil.sidebarOpen");
    if (stored !== null) setSidebarOpen(stored === "true");
  }, []);
  useEffect(() => {
    localStorage.setItem("coreveil.sidebarOpen", String(sidebarOpen));
  }, [sidebarOpen]);

  useEffect(() => {
    if (user) refreshConversations();
  }, [user]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Closes an open "..." menu on any click outside it, same as ChatGPT/Claude's own sidebar menus.
  useEffect(() => {
    if (menuOpenId === null) return;
    function handleClick(e: MouseEvent) {
      if (!(e.target as HTMLElement).closest(".convo-menu-wrap")) setMenuOpenId(null);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpenId]);

  useEffect(() => {
    if (renamingId !== null) renameInputRef.current?.focus();
  }, [renamingId]);

  async function refreshConversations() {
    try {
      const res = await authFetch(`/conversations`);
      if (res.ok) setConversations(await res.json());
    } catch {
      // Sidebar staying empty on a network hiccup isn't worth surfacing an error for.
    }
  }

  async function openConversation(id: number) {
    setActiveId(id);
    setMessages([]);
    const res = await authFetch(`/conversations/${id}/messages`);
    if (res.ok) {
      const data = await res.json();
      setMessages(data.map((m: any) => ({ role: m.role, text: m.content, citations: m.citations })));
    }
  }

  function startNewChat() {
    setActiveId(null);
    setMessages([]);
  }

  async function togglePin(convo: Conversation, e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpenId(null);
    const res = await authFetch(`/conversations/${convo.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned: !convo.pinned }),
    });
    if (res.ok) refreshConversations();
  }

  function startRename(convo: Conversation, e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpenId(null);
    setRenamingId(convo.id);
    setRenameValue(convo.title);
  }

  async function commitRename(convo: Conversation) {
    const title = renameValue.trim();
    setRenamingId(null);
    if (!title || title === convo.title) return;
    const res = await authFetch(`/conversations/${convo.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (res.ok) refreshConversations();
  }

  async function deleteConversation(convo: Conversation, e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpenId(null);
    if (!window.confirm(`Delete "${convo.title}"? This can't be undone.`)) return;
    const res = await authFetch(`/conversations/${convo.id}`, { method: "DELETE" });
    if (res.ok) {
      if (activeId === convo.id) startNewChat();
      refreshConversations();
    }
  }

  async function sendMessage(question: string) {
    if (!question.trim() || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await authFetch(`/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, conversation_id: activeId }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessages((prev) => [...prev, { role: "assistant", text: data.detail ?? "Something went wrong.", error: true }]);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", text: data.answer, citations: data.citations }]);
        if (activeId !== data.conversation_id) setActiveId(data.conversation_id);
        refreshConversations();
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", text: "Couldn't reach the backend.", error: true }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  return (
    <div className="app">
      <aside className={`sidebar ${sidebarOpen ? "" : "closed"}`}>
        <div className="sidebar-header">
          <span className="brand">
            <span className="logo-mark" />
            <span className="mark">Coreveil</span>
          </span>
          <button className="icon-btn" onClick={() => setSidebarOpen(false)} aria-label="Collapse sidebar">
            <PanelIcon />
          </button>
        </div>

        <button className="new-chat-btn" onClick={startNewChat}>
          <PlusIcon /> New chat
        </button>

        <div className="convo-list">
          {conversations.length === 0 && <div className="sidebar-empty">No conversations yet.</div>}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`convo-item ${c.id === activeId ? "active" : ""}`}
              onClick={() => (renamingId === c.id ? undefined : openConversation(c.id))}
            >
              {c.pinned && (
                <span className="convo-pin-indicator">
                  <PinIcon filled />
                </span>
              )}

              {renamingId === c.id ? (
                <input
                  ref={renameInputRef}
                  className="convo-rename-input"
                  value={renameValue}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => commitRename(c)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); commitRename(c); }
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                />
              ) : (
                <span className="convo-title">{c.title}</span>
              )}

              <div className="convo-menu-wrap">
                <button
                  className="menu-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpenId(menuOpenId === c.id ? null : c.id);
                  }}
                  aria-label="Chat options"
                >
                  <DotsIcon />
                </button>

                {menuOpenId === c.id && (
                  <div className="convo-menu">
                    <button onClick={(e) => togglePin(c, e)}>
                      <PinIcon filled={c.pinned} /> {c.pinned ? "Unpin" : "Pin"}
                    </button>
                    <button onClick={(e) => startRename(c, e)}>
                      <EditIcon /> Rename
                    </button>
                    <button className="danger" onClick={(e) => deleteConversation(c, e)}>
                      <TrashIcon /> Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {user && (
          <div className="sidebar-footer">
            <span className="user-chip">
              <span className="user-avatar">{user.name.charAt(0).toUpperCase()}</span>
              <span className="user-info">
                <span className="user-name">{user.name}</span>
                <span className="user-email">{user.email}</span>
              </span>
            </span>
            <button className="icon-btn" onClick={logout} aria-label="Log out" title="Log out">
              <LogoutIcon />
            </button>
          </div>
        )}
      </aside>

      <div className="shell">
        <header className="header">
          {!sidebarOpen && (
            <button className="icon-btn reopen-btn" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
              <PanelIcon />
            </button>
          )}
          <span className="brand">
            <span className="logo-mark" />
            <span className="mark header-mark">Coreveil</span>
          </span>
          <span className="tagline">Internal Knowledge Assistant</span>
          <Link href="/upload" className="nav-link">
            Upload documents
          </Link>
        </header>

        <main className="main">
          <div className="thread">
            {messages.length === 0 && (
              <div className="empty">
                <div className="icon">
                  <SparkleIcon />
                </div>
                <h2>Ask anything about the indexed documents</h2>
                <div className="suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="suggestion" onClick={() => sendMessage(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`row ${m.role}`}>
                {m.role === "assistant" && <span className="label">Coreveil</span>}
                <div className={`bubble ${m.error ? "error" : ""}`}>
                  {m.role === "assistant" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeRaw, rehypeSanitize]}
                    >
                      {m.text}
                    </ReactMarkdown>
                  ) : (
                    m.text
                  )}
                </div>
                {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                  <div className="citations">
                    {m.citations.map((c, j) => (
                      <button
                        key={j}
                        className="citation"
                        title={`Download ${c.filename}`}
                        onClick={() => downloadDocument(c.document_id, c.filename)}
                      >
                        <span className="dot-mark" />
                        {c.filename} — p.{c.page_number}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="row assistant">
                <span className="label">Coreveil</span>
                <div className="thinking">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}

            <div ref={threadEndRef} />
          </div>
        </main>

        <div className="composer">
          <div className="composer-inner">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
            />
            <button
              className="send-btn"
              disabled={!input.trim() || loading}
              onClick={() => sendMessage(input)}
              aria-label="Send"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M4 12L20 4L14 20L11 13L4 12Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PanelIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="1.6" />
      <line x1="9.5" y1="4" x2="9.5" y2="20" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M12 4V20M4 12H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function PinIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"}>
      <path
        d="M12 2L14 8L20 10L14.5 14L15 21L12 17.5L9 21L9.5 14L4 10L10 8L12 2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 2.5L14 9L20.5 11L14 13L12 19.5L10 13L3.5 11L10 9L12 2.5Z"
        fill="currentColor"
      />
    </svg>
  );
}

function DotsIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
      <path d="M17 3a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" />
    </svg>
  );
}
