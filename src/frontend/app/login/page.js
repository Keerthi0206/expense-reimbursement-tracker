"use client";

import { useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { useTheme } from "../../lib/theme-context";

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function LoginPage() {
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
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
    <div className="center-shell" style={{ position: "relative" }}>
      <button
        className="theme-toggle theme-toggle-paper"
        onClick={toggleTheme}
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        style={{ position: "absolute", top: 20, right: 20 }}
      >
        {theme === "dark" ? <SunIcon /> : <MoonIcon />}
      </button>
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
