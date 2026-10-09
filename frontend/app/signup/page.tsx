"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_URL, setSession } from "../lib/auth";
import PasswordField from "../components/PasswordField";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
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
      const res = await fetch(`${API_URL}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Couldn't create your account.");
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
          <span className="logo-mark" />
          <span className="mark header-mark">mindbuilt.ai</span>
        </span>
        <p className="auth-sub">
          Create an account to get started. <span className="auth-note">Open to anyone for now — this will be
          restricted to DKK employees once real access rules are set up.</span>
        </p>

        <form onSubmit={handleSubmit}>
          <label className="auth-label">
            Name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              placeholder="Jane Doe"
            />
          </label>
          <label className="auth-label">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@dkkcinc.com"
            />
          </label>
          <label className="auth-label">
            Password
            <PasswordField
              value={password}
              onChange={setPassword}
              minLength={8}
              placeholder="At least 8 characters"
            />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="pill-btn primary auth-submit" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
