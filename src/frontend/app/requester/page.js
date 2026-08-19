"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import RequireAuth from "../../lib/require-auth";
import LoadingState from "../../components/LoadingState";
import { api } from "../../lib/api";
import RequestRow from "../../components/RequestRow";
import { useFocusOnError } from "../../lib/useFocusOnError";

function RequesterHome() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState(null);
  const [statusFilter, setStatusFilter] = useState(() => searchParams.get("status") || "");
  const [categoryFilter, setCategoryFilter] = useState(() => searchParams.get("category") || "");
  const [keyword, setKeyword] = useState(() => searchParams.get("q") || "");
  const [page, setPage] = useState(() => parseInt(searchParams.get("page") || "1", 10) || 1);
  const [error, setError] = useState("");
  const errorRef = useFocusOnError(error);

  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (categoryFilter) params.set("category", categoryFilter);
    if (keyword) params.set("q", keyword);
    if (page !== 1) params.set("page", String(page));
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }, [statusFilter, categoryFilter, keyword, page, router]);

  const load = useCallback(async () => {
    try {
      const result = await api.listRequests({
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        keyword: keyword || undefined,
        page,
        page_size: 10,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    }
  }, [statusFilter, categoryFilter, keyword, page]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Requester</div>
          <h1>My Requests</h1>
        </div>
        <Link href="/requester/new" className="btn btn-primary">
          + New Request
        </Link>
      </div>

      {error && <div className="banner banner-error" role="alert" ref={errorRef} tabIndex={-1}>{error}</div>}

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
            <option value="draft">Draft</option>
            <option value="pending">Pending review (Submitted + Under Review)</option>
            <option value="submitted">Submitted only</option>
            <option value="under_review">Under Review only</option>
            <option value="changes_requested">Changes Requested</option>
            <option value="pending_second_approval">Pending 2nd Approval</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
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
        <div className="filter-field" style={{ flex: 1, minWidth: 180 }}>
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
        {(statusFilter || categoryFilter || keyword) && (
          <div className="filter-field">
            <label className="filter-field-label">&nbsp;</label>
            <button
              className="btn btn-sm"
              onClick={() => { setStatusFilter(""); setCategoryFilter(""); setKeyword(""); setPage(1); }}
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {!data ? (
        <LoadingState />
      ) : data.items.length === 0 ? (
        <div className="empty-state">
          <p>No requests match these filters yet.</p>
          <Link href="/requester/new" className="btn btn-primary" style={{ marginTop: 12 }}>
            Create your first request
          </Link>
        </div>
      ) : (
        <>
          {data.items.map((r) => (
            <RequestRow key={r.id} request={r} />
          ))}
          {data.total_pages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
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
    <RequireAuth roles={["requester", "admin"]}>
      <Suspense fallback={<LoadingState />}>
        <RequesterHome />
      </Suspense>
    </RequireAuth>
  );
}
