"use client";

import { useEffect, useState, useCallback } from "react";
import RequireAuth from "../../lib/require-auth";
import { api } from "../../lib/api";
import RequestRow from "../../components/RequestRow";

const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  under_review: "Under Review",
  changes_requested: "Changes Requested",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
  cancelled: "Cancelled",
};

function ReviewerHome() {
  const [dashboard, setDashboard] = useState(null);
  const [data, setData] = useState(null);
  const [requesters, setRequesters] = useState([]);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [requesterFilter, setRequesterFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [keyword, setKeyword] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(() => {
    api.dashboard().then(setDashboard).catch((err) => setError(err.message));
  }, []);

  const loadRequesters = useCallback(() => {
    api.listRequesters().then(setRequesters).catch(() => {
      // Non-critical — the filter dropdown just won't populate if this fails.
    });
  }, []);

  const loadRequests = useCallback(async () => {
    try {
      const result = await api.listRequests({
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        requester_id: requesterFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        min_amount: minAmount || undefined,
        max_amount: maxAmount || undefined,
        keyword: keyword || undefined,
        sort_by: sortBy,
        order,
        page,
        page_size: 10,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    }
  }, [statusFilter, categoryFilter, requesterFilter, dateFrom, dateTo, minAmount, maxAmount, keyword, sortBy, order, page]);

  useEffect(() => {
    loadDashboard();
    loadRequesters();
  }, [loadDashboard, loadRequesters]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  function clearFilters() {
    setStatusFilter("");
    setCategoryFilter("");
    setRequesterFilter("");
    setDateFrom("");
    setDateTo("");
    setMinAmount("");
    setMaxAmount("");
    setKeyword("");
    setSortBy("created_at");
    setOrder("desc");
    setPage(1);
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Reviewer</div>
          <h1>Review Queue</h1>
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {dashboard && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="label">Total Requested</div>
            <div className="value">${dashboard.total_requested.toFixed(2)}</div>
          </div>
          <div className="stat-tile">
            <div className="label">Total Pending</div>
            <div className="value">${dashboard.total_pending.toFixed(2)}</div>
          </div>
          <div className="stat-tile">
            <div className="label">Total Approved</div>
            <div className="value">${dashboard.total_approved.toFixed(2)}</div>
          </div>
          <div className="stat-tile">
            <div className="label">Total Paid</div>
            <div className="value">${dashboard.total_paid.toFixed(2)}</div>
          </div>
        </div>
      )}

      {dashboard && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Requests by status
          </div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {Object.entries(dashboard.count_by_status).map(([status, count]) => (
              <div key={status} style={{ fontSize: "0.85rem" }}>
                <span className="mono" style={{ fontWeight: 600 }}>
                  {count}
                </span>{" "}
                <span style={{ color: "var(--ink-soft)" }}>{STATUS_LABELS[status] || status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="filter-bar">
        <div className="filter-field">
          <label className="filter-field-label">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending review (Submitted + Under Review)</option>
            <option value="submitted">Submitted only</option>
            <option value="under_review">Under Review only</option>
            <option value="changes_requested">Changes Requested (awaiting requester)</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
            <option value="draft">Draft</option>
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">Category</label>
          <select
            value={categoryFilter}
            onChange={(e) => {
              setCategoryFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All categories</option>
            <option value="travel">Travel</option>
            <option value="meals">Meals</option>
            <option value="office_supplies">Office Supplies</option>
            <option value="software_subscriptions">Software / Subscriptions</option>
            <option value="event_expenses">Event Expenses</option>
            <option value="training">Training</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">Requester</label>
          <select
            value={requesterFilter}
            onChange={(e) => {
              setRequesterFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All requesters</option>
            {requesters.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">Expense date</label>
          <div className="filter-range">
            <input
              type="date"
              aria-label="From date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
            />
            <span>to</span>
            <input
              type="date"
              aria-label="To date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">Amount</label>
          <div className="filter-range">
            <input
              type="number"
              step="0.01"
              min="0"
              placeholder="Min"
              aria-label="Minimum amount"
              style={{ width: 80 }}
              value={minAmount}
              onChange={(e) => {
                setMinAmount(e.target.value);
                setPage(1);
              }}
            />
            <span>to</span>
            <input
              type="number"
              step="0.01"
              min="0"
              placeholder="Max"
              aria-label="Maximum amount"
              style={{ width: 80 }}
              value={maxAmount}
              onChange={(e) => {
                setMaxAmount(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">Search</label>
          <input
            type="text"
            placeholder="Title or description…"
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
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
            <option value="amount:desc">Amount: high to low</option>
            <option value="amount:asc">Amount: low to high</option>
            <option value="expense_date:desc">Expense date: newest</option>
            <option value="expense_date:asc">Expense date: oldest</option>
            <option value="title:asc">Title: A to Z</option>
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-field-label">&nbsp;</label>
          <button className="btn btn-sm" onClick={clearFilters}>
            Clear filters
          </button>
        </div>
      </div>

      {!data ? (
        <p>Loading…</p>
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <p>Nothing here right now.</p>
        </div>
      ) : (
        <>
          {data.items.map((r) => (
            <RequestRow key={r.id} request={r} showRequester />
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
    <RequireAuth roles={["reviewer", "admin"]}>
      <ReviewerHome />
    </RequireAuth>
  );
}
