"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import RequireAuth from "../../../lib/require-auth";
import { useAuth } from "../../../lib/auth-context";
import { api } from "../../../lib/api";
import StatusStamp from "../../../components/StatusStamp";
import { CATEGORY_LABELS } from "../../../components/RequestRow";

const TODAY = new Date().toISOString().slice(0, 10);

function RequestDetail() {
  const { id } = useParams();
  const router = useRouter();
  const { user } = useAuth();

  const [request, setRequest] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [infoMessage, setInfoMessage] = useState("");
  const [showInfoForm, setShowInfoForm] = useState(false);
  const [receiptUrl, setReceiptUrl] = useState(null);

  // Draft-editing state (only used when the owner is editing their own draft)
  const [editTitle, setEditTitle] = useState("");
  const [editAmount, setEditAmount] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editReceiptFile, setEditReceiptFile] = useState(null);
  const [editFieldErrors, setEditFieldErrors] = useState({});

  const load = useCallback(async () => {
    try {
      const data = await api.getRequest(id);
      setRequest(data);
      setEditTitle(data.title);
      setEditAmount(String(data.amount));
      setEditDate(data.expense_date);
      setEditCategory(data.category);
      setEditDescription(data.description || "");
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const isReviewer = user && (user.role === "reviewer" || user.role === "admin");
  const isOwner = request && user && request.requester.id === user.id;
  // Owner can edit while it's a draft, or while the reviewer has sent it back for more info.
  const isOwnerEditable = isOwner && request && ["draft", "changes_requested"].includes(request.status);
  const canReviewSubmitted =
    isReviewer && request && !isOwner && ["submitted", "under_review"].includes(request.status);
  const canRequestInfo = canReviewSubmitted; // same eligibility as approve/reject
  // A reviewer can revoke a mistaken approval (reject with a reason) any time before payment.
  const canRevokeApproval = isReviewer && request && !isOwner && request.status === "approved";
  const canMarkPaid = isReviewer && request && !isOwner && request.status === "approved";

  async function handleViewReceipt() {
    try {
      const url = await api.fetchReceiptBlobUrl(id);
      setReceiptUrl(url);
      window.open(url, "_blank");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleApprove() {
    setBusy(true);
    setError("");
    try {
      await api.approveRequest(id, comment || undefined);
      await load();
      setComment("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject(e) {
    e.preventDefault();
    if (!rejectReason.trim()) {
      setError("A rejection reason is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.rejectRequest(id, rejectReason.trim());
      await load();
      setShowRejectForm(false);
      setRejectReason("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkPaid() {
    setBusy(true);
    setError("");
    try {
      await api.markPaid(id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRequestInfo(e) {
    e.preventDefault();
    if (!infoMessage.trim()) {
      setError("A message explaining what's needed is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.requestInfo(id, infoMessage.trim());
      await load();
      setShowInfoForm(false);
      setInfoMessage("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function validateEdits() {
    const errs = {};
    if (!editTitle.trim()) errs.title = "Title is required.";
    const numAmount = parseFloat(editAmount);
    if (!editAmount || isNaN(numAmount) || numAmount <= 0) errs.amount = "Amount must be greater than zero.";
    if (!editDate) errs.date = "Expense date is required.";
    else if (editDate > TODAY) errs.date = "Expense date cannot be in the future.";
    if (!editCategory) errs.category = "Please select a category.";
    return errs;
  }

  async function handleSaveDraftEdits() {
    setError("");
    const errs = validateEdits();
    setEditFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setBusy(true);
    try {
      await api.updateRequest(id, {
        title: editTitle.trim(),
        amount: parseFloat(editAmount),
        expense_date: editDate,
        category: editCategory,
        description: editDescription.trim() || undefined,
      });
      if (editReceiptFile) {
        await api.uploadReceipt(id, editReceiptFile);
        setEditReceiptFile(null);
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitDraft() {
    setError("");
    const errs = validateEdits();
    if (!request.receipt_filename && !editReceiptFile) {
      errs.receipt = "A receipt must be attached before submitting.";
    }
    setEditFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setBusy(true);
    try {
      await api.updateRequest(id, {
        title: editTitle.trim(),
        amount: parseFloat(editAmount),
        expense_date: editDate,
        category: editCategory,
        description: editDescription.trim() || undefined,
      });
      if (editReceiptFile) {
        await api.uploadReceipt(id, editReceiptFile);
        setEditReceiptFile(null);
      }
      await api.submitRequest(id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !request) {
    return <div className="banner banner-error">{error}</div>;
  }
  if (!request) return <p>Loading…</p>;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Reimbursement Request</div>
          <h1>{request.title}</h1>
        </div>
        <StatusStamp status={request.status} />
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      <div className="card">
        <div className="form-row">
          <div>
            <div className="eyebrow">Amount</div>
            <div className="amount" style={{ fontSize: "1.3rem", fontWeight: 600 }}>
              ${request.amount.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="eyebrow">Expense date</div>
            <div>{request.expense_date}</div>
          </div>
        </div>
        <div className="form-row" style={{ marginTop: 16 }}>
          <div>
            <div className="eyebrow">Category</div>
            <div>{CATEGORY_LABELS[request.category] || request.category}</div>
          </div>
          <div>
            <div className="eyebrow">Requester</div>
            <div>
              {request.requester.name} ({request.requester.email})
            </div>
          </div>
        </div>
        {request.description && (
          <div style={{ marginTop: 16 }}>
            <div className="eyebrow">Description</div>
            <div>{request.description}</div>
          </div>
        )}
        <div style={{ marginTop: 16 }}>
          <div className="eyebrow">Receipt</div>
          {request.receipt_filename ? (
            <button className="btn btn-sm" onClick={handleViewReceipt}>
              View {request.receipt_filename}
            </button>
          ) : (
            <span style={{ color: "var(--ink-soft)" }}>No receipt attached</span>
          )}
        </div>

        {request.status === "rejected" && request.rejection_reason && (
          <div className="banner banner-error" style={{ marginTop: 16 }}>
            <strong>Rejection reason:</strong> {request.rejection_reason}
          </div>
        )}
        {request.status === "changes_requested" && request.info_requested_message && (
          <div className="banner" style={{ marginTop: 16, background: "var(--stamp-ochre-soft)", color: "var(--stamp-ochre)", border: "1px solid #e8d4a8" }}>
            <strong>Reviewer requested more information:</strong> {request.info_requested_message}
          </div>
        )}
        {request.reviewer_comment && request.status !== "rejected" && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>
            <strong>Reviewer comment:</strong> {request.reviewer_comment}
          </div>
        )}
      </div>

      {isOwnerEditable && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            {request.status === "changes_requested" ? "Update and resubmit" : "Edit draft"}
          </div>
          {request.status === "changes_requested" && (
            <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0, marginBottom: 16 }}>
              Address the reviewer&rsquo;s note above, then resubmit for review.
            </p>
          )}
          <div className="field">
            <label htmlFor="edit-title">Expense title</label>
            <input id="edit-title" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
            {editFieldErrors.title && <div className="field-error">{editFieldErrors.title}</div>}
          </div>
          <div className="form-row">
            <div className="field">
              <label htmlFor="edit-amount">Amount (USD)</label>
              <input
                id="edit-amount"
                type="number"
                step="0.01"
                min="0.01"
                value={editAmount}
                onChange={(e) => setEditAmount(e.target.value)}
              />
              {editFieldErrors.amount && <div className="field-error">{editFieldErrors.amount}</div>}
            </div>
            <div className="field">
              <label htmlFor="edit-date">Expense date</label>
              <input
                id="edit-date"
                type="date"
                max={TODAY}
                value={editDate}
                onChange={(e) => setEditDate(e.target.value)}
              />
              {editFieldErrors.date && <div className="field-error">{editFieldErrors.date}</div>}
            </div>
          </div>
          <div className="field">
            <label htmlFor="edit-category">Category</label>
            <select id="edit-category" value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
              <option value="">Select a category…</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            {editFieldErrors.category && <div className="field-error">{editFieldErrors.category}</div>}
          </div>
          <div className="field">
            <label htmlFor="edit-description">Description / business justification</label>
            <textarea
              id="edit-description"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="edit-receipt">
              {request.receipt_filename ? "Replace receipt (optional)" : "Attach receipt (required to submit)"}
            </label>
            <input
              id="edit-receipt"
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              onChange={(e) => setEditReceiptFile(e.target.files?.[0] || null)}
            />
            {editReceiptFile && (
              <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)", marginTop: 4 }}>
                Selected: {editReceiptFile.name}
              </div>
            )}
            {editFieldErrors.receipt && <div className="field-error">{editFieldErrors.receipt}</div>}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn" onClick={handleSaveDraftEdits} disabled={busy}>
              {busy ? "Saving…" : "Save without submitting"}
            </button>
            <button className="btn btn-primary" onClick={handleSubmitDraft} disabled={busy}>
              {busy
                ? (request.status === "changes_requested" ? "Resubmitting…" : "Submitting…")
                : (request.status === "changes_requested" ? "Resubmit for review" : "Submit for review")}
            </button>
          </div>
        </div>
      )}

      {canReviewSubmitted && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            Review this request
          </div>

          {!showRejectForm && !showInfoForm ? (
            <>
              <div className="field">
                <label htmlFor="comment">Comment (optional, shown on approval)</label>
                <textarea
                  id="comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Any notes for the requester…"
                />
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button className="btn btn-approve" onClick={handleApprove} disabled={busy}>
                  Approve
                </button>
                <button
                  className="btn btn-reject"
                  onClick={() => setShowRejectForm(true)}
                  disabled={busy}
                >
                  Reject
                </button>
                <button
                  className="btn"
                  onClick={() => setShowInfoForm(true)}
                  disabled={busy}
                >
                  Request more information
                </button>
              </div>
            </>
          ) : showRejectForm ? (
            <form onSubmit={handleReject}>
              <div className="field">
                <label htmlFor="reason">Rejection reason (required)</label>
                <textarea
                  id="reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Explain why this request is being rejected…"
                  required
                />
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="submit" className="btn btn-reject" disabled={busy}>
                  Confirm rejection
                </button>
                <button type="button" className="btn" onClick={() => setShowRejectForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={handleRequestInfo}>
              <div className="field">
                <label htmlFor="info-message">What do you need from the requester? (required)</label>
                <textarea
                  id="info-message"
                  value={infoMessage}
                  onChange={(e) => setInfoMessage(e.target.value)}
                  placeholder="e.g. The receipt is illegible — please re-upload a clearer copy…"
                  required
                />
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  Send request
                </button>
                <button type="button" className="btn" onClick={() => setShowInfoForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {canMarkPaid && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            Payment
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0 }}>
            This request is approved and awaiting payment.
          </p>
          <button className="btn btn-approve" onClick={handleMarkPaid} disabled={busy}>
            Mark as Paid
          </button>
        </div>
      )}

      {canRevokeApproval && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            Approved by mistake?
          </div>
          {!showRejectForm ? (
            <>
              <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0 }}>
                If this request was approved in error, you can reverse the approval with a reason —
                this is only possible before it&rsquo;s marked Paid.
              </p>
              <button className="btn btn-reject" onClick={() => setShowRejectForm(true)} disabled={busy}>
                Reject / reverse approval
              </button>
            </>
          ) : (
            <form onSubmit={handleReject}>
              <div className="field">
                <label htmlFor="revoke-reason">Reason for reversing this approval (required)</label>
                <textarea
                  id="revoke-reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Explain why this approval is being reversed…"
                  required
                />
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="submit" className="btn btn-reject" disabled={busy}>
                  Confirm reversal
                </button>
                <button type="button" className="btn" onClick={() => setShowRejectForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      <div className="card">
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          History
        </div>
        {request.history.length === 0 ? (
          <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem" }}>No history yet.</p>
        ) : (
          request.history
            .slice()
            .reverse()
            .map((h) => (
              <div key={h.id} className="history-item">
                <div className="history-time">
                  {new Date(h.timestamp).toLocaleString()}
                </div>
                <div>
                  <strong>{h.action.replace(/_/g, " ")}</strong>
                  {h.previous_status && h.new_status ? ` — ${h.previous_status} → ${h.new_status}` : ""}
                  {h.comment ? `: ${h.comment}` : ""}
                </div>
              </div>
            ))
        )}
      </div>
    </>
  );
}

export default function Page() {
  return (
    <RequireAuth roles={["requester", "reviewer", "admin"]}>
      <RequestDetail />
    </RequireAuth>
  );
}
