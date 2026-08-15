"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../lib/auth-context";
import { useTheme } from "../lib/theme-context";
import { api } from "../lib/api";

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

export default function Nav() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const pathname = usePathname();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (!user) return;
    api
      .notifications({ page_size: 100 })
      .then((data) => setUnreadCount(data.items.filter((n) => !n.is_read).length))
      .catch(() => {
        // Non-critical — the badge just won't show if this fails.
      });
  }, [user, pathname]);

  if (!user) return null;

  const isReviewer = user.role === "reviewer" || user.role === "admin";
  const isRequester = user.role === "requester";

  return (
    <div className="topbar">
      <div className="brand">
        <span className="mark">CDF Ledger</span>
        <span className="sub">Expense &amp; Reimbursement Tracker</span>
      </div>
      <div className="nav">
        {isReviewer && (
          <Link href="/reviewer" className={pathname === "/reviewer" ? "active" : ""}>
            Review Queue
          </Link>
        )}
        {isRequester && (
          <>
            <Link href="/requester" className={pathname === "/requester" ? "active" : ""}>
              My Requests
            </Link>
            <Link href="/requester/new" className={pathname === "/requester/new" ? "active" : ""}>
              New Request
            </Link>
          </>
        )}
        {user.role === "admin" && (
          <Link href="/admin" className={pathname.startsWith("/admin") ? "active" : ""}>
            Admin
          </Link>
        )}
        <Link
          href="/notifications"
          className={pathname === "/notifications" ? "active" : ""}
          style={{ display: "flex", alignItems: "center", gap: 6 }}
        >
          Notifications
          {unreadCount > 0 && (
            <span
              style={{
                background: "var(--stamp-brick)",
                color: "var(--action-text)",
                borderRadius: 999,
                fontSize: "0.68rem",
                fontWeight: 600,
                padding: "1px 6px",
                minWidth: 16,
                textAlign: "center",
                lineHeight: "16px",
              }}
            >
              {unreadCount}
            </span>
          )}
        </Link>
      </div>
      <div className="who">
        <span>{user.name}</span>
        <span className="role-chip">{user.role}</span>
        <button
          className="theme-toggle theme-toggle-cover"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        <button className="logout-btn" onClick={logout}>
          Log out
        </button>
      </div>
    </div>
  );
}
