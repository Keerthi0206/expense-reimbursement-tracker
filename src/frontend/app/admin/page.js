"use client";

import { useEffect, useState, useCallback } from "react";
import RequireAuth from "../../lib/require-auth";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";

const ROLE_LABELS = { admin: "Admin", reviewer: "Reviewer", requester: "Requester" };

function formatDate(iso) {
  return new Date(iso).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function AdminPage() {
  const { user: currentUser } = useAuth();
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [expandedHistory, setExpandedHistory] = useState({}); // userId -> history[] | "loading"
  const [reminderBusy, setReminderBusy] = useState(false);
  const [reminderMessage, setReminderMessage] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [order, setOrder] = useState("desc");

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("requester");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await api.listUsers({
        page, page_size: 10,
        role: roleFilter || undefined,
        is_active: statusFilter || undefined,
        search: search || undefined,
        sort_by: sortBy, order,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    }
  }, [page, roleFilter, statusFilter, search, sortBy, order]);

  useEffect(() => {
    load();
  }, [load]);

  const users = data?.items || [];

  async function handleRoleChange(userId, newRoleValue) {
    const reason = window.prompt(
      `Optional: why are you changing this user's role to "${newRoleValue}"? (Cancel to abort the change)`
    );
    if (reason === null) return; // user hit Cancel — abort the whole change
    setBusyId(userId);
    setError("");
    try {
      await api.updateUserRole(userId, newRoleValue, reason || undefined);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleStatusToggle(userId, currentlyActive) {
    const action = currentlyActive ? "deactivating" : "activating";
    const reason = window.prompt(
      `Optional: why are you ${action} this account? (Cancel to abort)`
    );
    if (reason === null) return;
    setBusyId(userId);
    setError("");
    try {
      await api.updateUserStatus(userId, !currentlyActive, reason || undefined);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function toggleHistory(userId) {
    if (expandedHistory[userId]) {
      setExpandedHistory((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
      return;
    }
    setExpandedHistory((prev) => ({ ...prev, [userId]: "loading" }));
    try {
      const result = await api.getUserHistory(userId);
      setExpandedHistory((prev) => ({ ...prev, [userId]: result.items }));
    } catch (err) {
      setError(err.message);
      setExpandedHistory((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    }
  }

  async function handleTriggerReminders() {
    setReminderBusy(true);
    setReminderMessage("");
    setError("");
    try {
      const result = await api.triggerReminders();
      setReminderMessage(
        result.reminders_sent === 0
          ? `No requests have been pending longer than ${result.threshold_days} days.`
          : `Sent reminders for ${result.reminders_sent} request(s) pending over ${result.threshold_days} days.`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setReminderBusy(false);
    }
  }

  async function handleCreateUser(e) {
    e.preventDefault();
    setCreateError("");
    if (!newName.trim() || !newEmail.trim() || newPassword.length < 6) {
      setCreateError("Name, email, and a password of at least 6 characters are required.");
      return;
    }
    setCreateBusy(true);
    try {
      await api.createUser({ name: newName.trim(), email: newEmail.trim(), password: newPassword, role: newRole });
      setNewName("");
      setNewEmail("");
      setNewPassword("");
      setNewRole("requester");
      setShowCreateForm(false);
      await load();
    } catch (err) {
      setCreateError(err.message);
    } finally {
      setCreateBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Administration</div>
          <h1>User Accounts</h1>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn btn-sm" onClick={handleTriggerReminders} disabled={reminderBusy}>
            {reminderBusy ? "Checking…" : "Send pending-review reminders now"}
          </button>
          <button className="btn" onClick={() => setShowCreateForm((v) => !v)}>
            {showCreateForm ? "Cancel" : "+ New user"}
          </button>
        </div>
      </div>

      {reminderMessage && <div className="banner banner-success">{reminderMessage}</div>}
      {error && <div className="banner banner-error">{error}</div>}

      <div className="filter-bar">
        <div className="filter-field">
          <label className="filter-field-label">Role</label>
          <select value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}>
            <option value="">All roles</option>
            <option value="requester">Requester</option>
            <option value="reviewer">Reviewer</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="filter-field">
          <label className="filter-field-label">Status</label>
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}>
            <option value="">All accounts</option>
            <option value="true">Active only</option>
            <option value="false">Deactivated only</option>
          </select>
        </div>
        <div className="filter-field" style={{ flex: 1, minWidth: 180 }}>
          <label className="filter-field-label">Search</label>
          <input
            type="text"
            placeholder="Name or email…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="filter-field">
          <label className="filter-field-label">Sort by</label>
          <select
            value={`${sortBy}:${order}`}
            onChange={(e) => {
              const [nextSortBy, nextOrder] = e.target.value.split(":");
              setSortBy(nextSortBy);
              setOrder(nextOrder);
              setPage(1);
            }}
          >
            <option value="created_at:desc">Newest first</option>
            <option value="created_at:asc">Oldest first</option>
            <option value="name:asc">Name: A to Z</option>
            <option value="email:asc">Email: A to Z</option>
            <option value="role:asc">Role</option>
          </select>
        </div>
        {(roleFilter || statusFilter || search) && (
          <div className="filter-field">
            <label className="filter-field-label">&nbsp;</label>
            <button
              className="btn btn-sm"
              onClick={() => { setRoleFilter(""); setStatusFilter(""); setSearch(""); setPage(1); }}
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {showCreateForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="eyebrow" style={{ marginBottom: 12 }}>Create account</div>
          {createError && <div className="banner banner-error">{createError}</div>}
          <form onSubmit={handleCreateUser}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="new-name">Name</label>
                <input id="new-name" value={newName} onChange={(e) => setNewName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="new-email">Email (fictional)</label>
                <input id="new-email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="new-password">Temporary password</label>
                <input id="new-password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="new-role">Role</label>
                <select id="new-role" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                  <option value="requester">Requester</option>
                  <option value="reviewer">Reviewer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={createBusy}>
              {createBusy ? "Creating…" : "Create account"}
            </button>
          </form>
        </div>
      )}

      {users.length === 0 ? (
        <div className="empty-state">Loading users…</div>
      ) : (
        users.map((u) => {
          const isSelf = u.id === currentUser.id;
          const history = expandedHistory[u.id];
          return (
            <div key={u.id}>
              <div className="user-row">
                <div className="user-main">
                  <div className="user-name">
                    {u.name} {isSelf && <span style={{ color: "var(--ink-soft)", fontWeight: 400 }}>(you)</span>}
                  </div>
                  <div className="user-email">{u.email}</div>
                  <div className="user-meta">Created {formatDate(u.created_at)}</div>
                </div>

                <span className={`badge badge-role-${u.role}`}>{ROLE_LABELS[u.role] || u.role}</span>
                <span className={`badge ${u.is_active ? "badge-active" : "badge-inactive"}`}>
                  {u.is_active ? "Active" : "Inactive"}
                </span>

                <div className="user-actions">
                  <select
                    value={u.role}
                    disabled={isSelf || busyId === u.id}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    title={isSelf ? "You cannot change your own role" : "Change role"}
                  >
                    <option value="requester">Requester</option>
                    <option value="reviewer">Reviewer</option>
                    <option value="admin">Admin</option>
                  </select>

                  <button
                    className="btn btn-sm"
                    disabled={isSelf || busyId === u.id}
                    title={isSelf ? "You cannot deactivate your own account" : undefined}
                    onClick={() => handleStatusToggle(u.id, u.is_active)}
                  >
                    {u.is_active ? "Deactivate" : "Activate"}
                  </button>

                  <button className="btn btn-sm" onClick={() => toggleHistory(u.id)}>
                    {history ? "Hide history" : "View history"}
                  </button>
                </div>
              </div>

              {history && (
                <div className="card" style={{ marginTop: -6, marginBottom: 14 }}>
                  <div className="eyebrow" style={{ marginBottom: 8 }}>Role & status history</div>
                  {history === "loading" ? (
                    <div style={{ color: "var(--ink-soft)", fontSize: "0.85rem" }}>Loading…</div>
                  ) : history.length === 0 ? (
                    <div style={{ color: "var(--ink-soft)", fontSize: "0.85rem" }}>No changes recorded yet.</div>
                  ) : (
                    history.map((h) => (
                      <div key={h.id} className="history-item">
                        <span className="history-time">{formatDate(h.timestamp)}</span>
                        <span>
                          <strong>{h.action.replace(/_/g, " ")}</strong>
                          {h.previous_value && h.new_value && (
                            <> — {h.previous_value} → {h.new_value}</>
                          )}
                          {!h.previous_value && h.new_value && <> — {h.new_value}</>}
                          {h.reason && (
                            <span style={{ display: "block", color: "var(--ink-soft)", fontStyle: "italic" }}>
                              &ldquo;{h.reason}&rdquo;
                            </span>
                          )}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          );
        })
      )}

      {data && data.total_pages > 1 && (
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
  );
}

export default function Page() {
  return (
    <RequireAuth roles={["admin"]}>
      <AdminPage />
    </RequireAuth>
  );
}
