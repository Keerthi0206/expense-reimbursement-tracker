"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import RequireAuth from "../../lib/require-auth";
import { api } from "../../lib/api";

function formatDate(iso) {
  return new Date(iso).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function NotificationsPage() {
  const [notifications, setNotifications] = useState(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api.notifications();
      // Unread first, then newest first within each group.
      const sorted = [...data].sort((a, b) => {
        if (a.is_read !== b.is_read) return a.is_read ? 1 : -1;
        return new Date(b.created_at) - new Date(a.created_at);
      });
      setNotifications(sorted);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleMarkRead(id) {
    setBusyId(id);
    try {
      await api.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleMarkAllRead() {
    const unread = (notifications || []).filter((n) => !n.is_read);
    if (unread.length === 0) return;
    try {
      await Promise.all(unread.map((n) => api.markNotificationRead(n.id)));
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (err) {
      setError(err.message);
    }
  }

  const unreadCount = (notifications || []).filter((n) => !n.is_read).length;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Your notifications</div>
          <h1>Notifications</h1>
        </div>
        {unreadCount > 0 && (
          <button className="btn btn-sm" onClick={handleMarkAllRead}>
            Mark all as read
          </button>
        )}
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {!notifications ? (
        <p>Loading…</p>
      ) : notifications.length === 0 ? (
        <div className="empty-state">
          <p>No notifications yet.</p>
          <p style={{ fontSize: "0.85rem", marginTop: 4 }}>
            You&rsquo;ll see updates here when a request you&rsquo;re involved with changes status.
          </p>
        </div>
      ) : (
        notifications.map((n) => (
          <div
            key={n.id}
            className="card"
            style={{
              marginBottom: 10,
              borderLeft: n.is_read ? undefined : "4px solid var(--stamp-teal)",
              opacity: n.is_read ? 0.7 : 1,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontSize: "0.92rem" }}>{n.message}</p>
                <p style={{ margin: "6px 0 0", fontSize: "0.78rem", color: "var(--ink-soft)" }}>
                  {formatDate(n.created_at)}
                  {n.request_id && (
                    <>
                      {" · "}
                      <Link href={`/requests/${n.request_id}`} style={{ color: "var(--stamp-teal)" }}>
                        View request
                      </Link>
                    </>
                  )}
                </p>
              </div>
              {!n.is_read && (
                <button
                  className="btn btn-sm"
                  disabled={busyId === n.id}
                  onClick={() => handleMarkRead(n.id)}
                >
                  Mark as read
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </>
  );
}

export default function Page() {
  return (
    <RequireAuth roles={["requester", "reviewer", "admin"]}>
      <NotificationsPage />
    </RequireAuth>
  );
}
