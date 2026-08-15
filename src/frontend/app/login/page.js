"use client";

import { useState } from "react";
import { useAuth } from "../../lib/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  function fillDemo(demoEmail) {
    setEmail(demoEmail);
    setPassword("password123");
  }

  return (
    <div className="center-shell">
      <div className="login-card">
        <div className="eyebrow">Community Dreams Foundation</div>
        <h1 style={{ marginBottom: 6 }}>Expense Ledger</h1>
        <p style={{ color: "var(--ink-soft)", fontSize: "0.9rem", marginTop: 4, marginBottom: 24 }}>
          Sign in to submit or review reimbursement requests.
        </p>

        {error && <div className="banner banner-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="demo-creds">
          <strong>Demo accounts</strong> (password: password123)
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            <button className="btn btn-sm" type="button" onClick={() => fillDemo("alice@example.com")}>
              Requester — alice@example.com
            </button>
            <button className="btn btn-sm" type="button" onClick={() => fillDemo("rachel@example.com")}>
              Reviewer — rachel@example.com
            </button>
            <button className="btn btn-sm" type="button" onClick={() => fillDemo("admin@example.com")}>
              Admin — admin@example.com
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
