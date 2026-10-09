"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL, setSession } from "../lib/auth";
import PasswordField from "../components/PasswordField";
import Logo from "../components/Logo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Couldn't log in.");
        return;
      }
      setSession(data.token, data.user);
      router.push("/");
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <span className="brand auth-brand">
          <Logo size={30} />
          <span className="mark header-mark">mindbuilt.ai</span>
        </span>
        <p className="auth-sub">Internal Knowledge Assistant — sign in to continue</p>

        <form onSubmit={handleSubmit}>
          <label className="auth-label">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              placeholder="you@dkkcinc.com"
            />
          </label>
          <label className="auth-label">
            Password
            <PasswordField value={password} onChange={setPassword} placeholder="••••••••" />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="pill-btn primary auth-submit" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="auth-switch">
          Don't have an account? <Link href="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  );
}
