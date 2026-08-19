"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import RequireAuth from "../../../lib/require-auth";
import { useAuth } from "../../../lib/auth-context";
import { api } from "../../../lib/api";
import { useFocusOnError } from "../../../lib/useFocusOnError";
import StatusStamp from "../../../components/StatusStamp";
import LoadingState from "../../../components/LoadingState";
import { CATEGORY_LABELS } from "../../../components/RequestRow";

const TODAY = new Date().toISOString().slice(0, 10);

function RequestDetail() {
  const { id } = useParams();
  const router = useRouter();
  const { user } = useAuth();

  const [request, setRequest] = useState(null);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const errorRef = useFocusOnError(error);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [infoMessage, setInfoMessage] = useState("");
  const [showInfoForm, setShowInfoForm] = useState(false);
  const [receiptUrl, setReceiptUrl] = useState(null);
  const [receiptAnalysis, setReceiptAnalysis] = useState(null);
  const [analyzingReceipt, setAnalyzingReceipt] = useState(false);

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
      return data;
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-fetch an inline thumbnail for image receipts once we know the
  // request has one -- PDFs stay as a plain "View" link/button below,
  // since inline PDF preview isn't worth the added complexity here.
  useEffect(() => {
    if (!request?.receipt_filename) return;
    const isImage = /\.(jpe?g|png)$/i.test(request.receipt_filename);
    if (!isImage) return;
    let cancelled = false;
    api.fetchReceiptBlobUrl(id).then((url) => {
      if (!cancelled) setReceiptUrl(url);
    }).catch(() => {
      // Non-critical -- the "View receipt" button still works as a fallback.
    });
    return () => { cancelled = true; };
  }, [request?.receipt_filename, id]);

  const isReviewer = user && (user.role === "reviewer" || user.role === "admin");
  const isOwner = request && user && request.requester.id === user.id;
  // Owner can edit while it's a draft, or while the reviewer has sent it back for more info.
  const isOwnerEditable =
    isOwner && request && ["draft", "changes_requested", "rejected"].includes(request.status);
  const canReviewSubmitted =
    isReviewer && request && !isOwner && ["submitted", "under_review"].includes(request.status);
  const canRequestInfo = canReviewSubmitted; // same eligibility as approve/reject
  // Second-tier approval (high-value/training) needs an admin -- backend enforces
  // the "not the same person as first approval" rule, shown here to any admin
  const canGiveSecondApproval =
    user && user.role === "admin" && request && !isOwner && request.status === "pending_second_approval";
  // A reviewer can revoke a mistaken approval (reject with a reason) any time before payment,
  // including while a second approval is still pending.
  const canRevokeApproval =
    isReviewer && request && !isOwner && ["approved", "pending_second_approval"].includes(request.status);
  const canMarkPaid = isReviewer && request && !isOwner && request.status === "approved";
  // Owner can cancel any time before a reviewer has made a final decision.
  const canCancel =
    isOwner && request && ["draft", "submitted", "under_review", "changes_requested"].includes(request.status);

  function showSuccess(message) {
    setSuccessMessage(message);
    setTimeout(() => setSuccessMessage(""), 5000);
  }

  async function handleViewReceipt() {
    try {
      const url = await api.fetchReceiptBlobUrl(id);
      setReceiptUrl(url);
      window.open(url, "_blank");
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCheckReceiptConsistency() {
    setAnalyzingReceipt(true);
    setError("");
    try {
      const result = await api.getReceiptAnalysis(id);
      setReceiptAnalysis(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setAnalyzingReceipt(false);
    }
  }

  async function handleApprove() {
    setBusy(true);
    setError("");
    try {
      await api.approveRequest(id, comment || undefined);
      const updated = await load();
      setComment("");
      if (updated?.status === "pending_second_approval") {
        showSuccess("First approval given — this now needs a second, admin-level approval.");
      } else {
        showSuccess("Request approved.");
      }
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
      showSuccess("Request rejected.");
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
      showSuccess("Marked as paid.");
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
      showSuccess("Sent back to the requester for more information.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    const confirmed = window.confirm(
      "Cancel this request? It will no longer be actionable, but stays in your history."
    );
    if (!confirmed) return;
    const reason = window.prompt("Optional: why are you cancelling this? (Cancel to skip)");
    setBusy(true);
    setError("");
    try {
      await api.cancelRequest(id, reason || undefined);
      await load();
      showSuccess("Request cancelled.");
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
      showSuccess("Draft saved.");
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
      showSuccess("Submitted for review.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !request) {
    return <div className="banner banner-error" role="alert" ref={errorRef} tabIndex={-1}>{error}</div>;
  }
  if (!request) return <LoadingState />;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Reimbursement Request</div>
          <h1>{request.title}</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {canCancel && (
            <button className="btn btn-sm btn-reject" onClick={handleCancel} disabled={busy}>
              Cancel request
            </button>
          )}
          <StatusStamp status={request.status} />
        </div>
      </div>

      {error && <div className="banner banner-error" role="alert" ref={errorRef} tabIndex={-1}>{error}</div>}
      {successMessage && <div className="banner banner-success" role="status">{successMessage}</div>}

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
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              {receiptUrl && /\.(jpe?g|png)$/i.test(request.receipt_filename) && (
                <button
                  onClick={handleViewReceipt}
                  aria-label="Open full-size receipt image"
                  style={{ padding: 0, border: "1px solid var(--line)", borderRadius: 4, background: "none", cursor: "pointer", lineHeight: 0 }}
                >
                  <img
                    src={receiptUrl}
                    alt="Receipt thumbnail"
                    style={{ width: 90, height: 90, objectFit: "cover", borderRadius: 3, display: "block" }}
                  />
                </button>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-start" }}>
                <button className="btn btn-sm" onClick={handleViewReceipt}>
                  View {request.receipt_filename}
                </button>
                <button className="btn btn-sm" onClick={handleCheckReceiptConsistency} disabled={analyzingReceipt}>
                  {analyzingReceipt ? "Checking…" : "Check receipt against submitted values"}
                </button>
              </div>
            </div>
          ) : (
            <span style={{ color: "var(--ink-soft)" }}>No receipt attached</span>
          )}

          {receiptAnalysis && (
            <div className="card" style={{ marginTop: 10, background: "var(--paper)" }}>
              <div style={{ fontSize: "0.78rem", color: "var(--ink-soft)", marginBottom: 8 }}>
                {receiptAnalysis.metadata.width && `${receiptAnalysis.metadata.width}×${receiptAnalysis.metadata.height}px · `}
                {receiptAnalysis.metadata.size_kb} KB
                {receiptAnalysis.metadata.page_count && ` · ${receiptAnalysis.metadata.page_count} page(s)`}
              </div>
              {!receiptAnalysis.amount_mismatch && !receiptAnalysis.date_mismatch ? (
                <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--stamp-teal)" }}>
                  ✓ The receipt appears to match the submitted amount and date.
                </p>
              ) : (
                <div style={{ fontSize: "0.85rem" }}>
                  <strong style={{ color: "var(--stamp-brick)" }}>Possible mismatch detected:</strong>
                  {receiptAnalysis.amount_mismatch && (
                    <p style={{ margin: "4px 0" }}>
                      Submitted amount is ${receiptAnalysis.submitted_amount.toFixed(2)}, but the receipt
                      appears to show ${receiptAnalysis.suggestion.suggested_amount.toFixed(2)}.
                    </p>
                  )}
                  {receiptAnalysis.date_mismatch && (
                    <p style={{ margin: "4px 0" }}>
                      Submitted date is {receiptAnalysis.submitted_date}, but the receipt appears to show{" "}
                      {receiptAnalysis.suggestion.suggested_date}.
                    </p>
                  )}
                  <p style={{ margin: "4px 0 0", color: "var(--ink-soft)", fontSize: "0.78rem" }}>
                    This is an automated read of the receipt image and can be wrong — use judgment,
                    not a rejection reason by itself.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {request.exceeds_budget && (
          <div className="banner" style={{ marginTop: 16, background: "var(--stamp-ochre-soft)", color: "var(--stamp-ochre)", border: "1px solid var(--stamp-ochre)" }}>
            <strong>Over budget:</strong> this exceeds the typical ${request.budget_limit.toFixed(0)} limit for {request.category.replace(/_/g, " ")}.
          </div>
        )}
        {request.status === "rejected" && request.rejection_reason && (
          <div className="banner banner-error" role="alert" style={{ marginTop: 16 }}>
            <strong>Rejection reason:</strong> {request.rejection_reason}
          </div>
        )}
        {request.status === "changes_requested" && request.info_requested_message && (
          <div className="banner" style={{ marginTop: 16, background: "var(--stamp-ochre-soft)", color: "var(--stamp-ochre)", border: "1px solid var(--stamp-ochre)" }}>
            <strong>Reviewer requested more information:</strong> {request.info_requested_message}
          </div>
        )}
        {request.reviewer_comment && request.status !== "rejected" && (
          <div className="banner banner-success" role="status" style={{ marginTop: 16 }}>
            <strong>Reviewer comment:</strong> {request.reviewer_comment}
          </div>
        )}
      </div>

      {isOwnerEditable && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            {request.status === "changes_requested"
              ? "Update and resubmit"
              : request.status === "rejected"
              ? "Fix and resubmit"
              : "Edit draft"}
          </div>
          {request.status === "changes_requested" && (
            <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0, marginBottom: 16 }}>
              Address the reviewer&rsquo;s note above, then resubmit for review.
            </p>
          )}
          {request.status === "rejected" && (
            <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0, marginBottom: 16 }}>
              Address the rejection reason above, then resubmit for review.
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
                ? (["changes_requested", "rejected"].includes(request.status) ? "Resubmitting…" : "Submitting…")
                : (["changes_requested", "rejected"].includes(request.status) ? "Resubmit for review" : "Submit for review")}
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

      {canGiveSecondApproval && (
        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 12 }}>
            Second approval needed
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0 }}>
            This request exceeds the normal approval threshold (or is a training expense) and needs
            a second, admin-level sign-off before it&rsquo;s fully approved. You cannot give this
            approval if you were the one who gave the first one.
          </p>
          <div className="field">
            <label htmlFor="second-approval-comment">Comment (optional)</label>
            <textarea
              id="second-approval-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Any notes for the requester…"
            />
          </div>
          <button className="btn btn-approve" onClick={handleApprove} disabled={busy}>
            Give second approval
          </button>
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
            {request.status === "pending_second_approval" ? "Reject instead?" : "Approved by mistake?"}
          </div>
          {!showRejectForm ? (
            <>
              <p style={{ fontSize: "0.85rem", color: "var(--ink-soft)", marginTop: 0 }}>
                {request.status === "pending_second_approval"
                  ? "If this shouldn't move forward, you can reject it here instead of waiting for a second approval."
                  : "If this request was approved in error, you can reverse the approval with a reason — this is only possible before it's marked Paid."}
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
