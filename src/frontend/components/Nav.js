"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";

export default function Nav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (!user) return;
    api
      .notifications()
      .then((data) => setUnreadCount(data.filter((n) => !n.is_read).length))
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
                background: "var(--stamp-brick, #a8433a)",
                color: "#fff",
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
        <button className="logout-btn" onClick={logout}>
          Log out
        </button>
      </div>
    </div>
  );
}
