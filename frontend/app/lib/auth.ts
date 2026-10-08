"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "coreveil.token";
const USER_KEY = "coreveil.user";

export type AuthUser = { id: number; name: string; email: string };

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Private browsing / blocked storage — session just won't survive a reload.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    // Nothing to do if storage is unavailable.
  }
}

/** fetch wrapper that attaches the auth header and redirects to /login on a 401 —
 * every page that calls the API should go through this instead of raw fetch(). */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearSession();
    window.location.href = "/login";
  }
  return res;
}

/** Downloads a document's original file through the authenticated endpoint
 * and saves it via the browser — used by both the library page and chat
 * citations, so a citation is a real "safe link to the original document,
 * subject to the same SQL permission check" (architecture doc Section
 * 4.7), not just a filename label. Returns false on failure so a caller
 * can show its own error state instead of failing silently. */
export async function downloadDocument(documentId: number, filename: string): Promise<boolean> {
  try {
    const res = await authFetch(`/documents/${documentId}/download`);
    if (!res.ok) return false;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    return true;
  } catch {
    return false;
  }
}

export { API_URL };
