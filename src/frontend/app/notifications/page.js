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
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [markingAll, setMarkingAll] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api.notifications({ page, page_size: 10 });
      setData(result);
    } catch (err) {
      setError(err.message);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleMarkRead(id) {
    setBusyId(id);
    try {
      await api.markNotificationRead(id);
      setData((prev) => ({
        ...prev,
        items: prev.items.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    try {
      // Fetch everything unread across all pages, not just what's currently visible.
      const all = await api.notifications({ page_size: 100 });
      const unread = all.items.filter((n) => !n.is_read);
      await Promise.all(unread.map((n) => api.markNotificationRead(n.id)));
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setMarkingAll(false);
    }
  }

  const notifications = data?.items || [];
  const hasUnreadOnPage = notifications.some((n) => !n.is_read);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Your notifications</div>
          <h1>Notifications</h1>
        </div>
        {(hasUnreadOnPage || (data && data.total_pages > 1)) && (
          <button className="btn btn-sm" onClick={handleMarkAllRead} disabled={markingAll}>
            {markingAll ? "Marking…" : "Mark all as read"}
          </button>
        )}
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {!data ? (
        <p>Loading…</p>
      ) : notifications.length === 0 ? (
        <div className="empty-state">
          <p>No notifications yet.</p>
          <p style={{ fontSize: "0.85rem", marginTop: 4 }}>
            You&rsquo;ll see updates here when a request you&rsquo;re involved with changes status.
          </p>
        </div>
      ) : (
        <>
          {notifications.map((n) => (
            <div
              key={n.id}
              className="card"
              style={{
                marginBottom: 10,
                borderLeft: n.is_read ? undefined : "4px solid var(--stamp-teal)",
                opacity: n.is_read ? 0.7 : 1,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
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
          ))}

          {data.total_pages > 1 && (
            <div className="pagination">
              <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <span>
                Page {data.page} of {data.total_pages} ({data.total} total)
              </span>
              <button
                className="btn btn-sm"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
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
