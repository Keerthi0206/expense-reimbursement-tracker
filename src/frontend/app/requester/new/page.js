"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import RequireAuth from "../../../lib/require-auth";
import { api } from "../../../lib/api";

const TODAY = new Date().toISOString().slice(0, 10);

// Mirrors backend/app/core/budget.py -- kept in sync manually since these are
// fixed constants, not admin-configurable. Used here only for an immediate
// warning as the requester types; the backend's computed `exceeds_budget`
// field on the actual response is still the authoritative value.
const CATEGORY_BUDGET_LIMITS = {
  travel: 800,
  meals: 150,
  office_supplies: 300,
  software_subscriptions: 500,
  event_expenses: 1000,
  training: 600,
  other: 300,
};

function NewRequestForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [expenseDate, setExpenseDate] = useState(TODAY);
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [receiptFile, setReceiptFile] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("form"); // form -> saved -> done
  const [duplicates, setDuplicates] = useState([]);
  const [confirmNotDuplicate, setConfirmNotDuplicate] = useState(false);
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null);
  const [suggestion, setSuggestion] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const debounceRef = useRef(null);

  useEffect(() => {
    const numAmount = parseFloat(amount);
    if (!amount || isNaN(numAmount) || numAmount <= 0 || !expenseDate) {
      setDuplicates([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      api
        .checkDuplicate(numAmount, expenseDate)
        .then(setDuplicates)
        .catch(() => setDuplicates([]));
    }, 500);
    return () => clearTimeout(debounceRef.current);
  }, [amount, expenseDate]);

  useEffect(() => {
    setConfirmNotDuplicate(false);
  }, [duplicates.length]);

  async function handleReceiptFileChange(file) {
    setReceiptFile(file);
    setSuggestion(null);

    if (receiptPreviewUrl) URL.revokeObjectURL(receiptPreviewUrl);
    setReceiptPreviewUrl(null);

    if (!file) return;

    // Client-side preview for images -- no server round-trip needed, we
    // already have the raw File object in the browser.
    if (file.type === "image/jpeg" || file.type === "image/png") {
      setReceiptPreviewUrl(URL.createObjectURL(file));
    }

    setExtracting(true);
    try {
      const result = await api.extractReceiptPreview(file);
      setSuggestion(result);
    } catch (err) {
      // Non-critical -- extraction failing just means no suggestions show up;
      // the requester can still fill in the form manually either way.
      setSuggestion(null);
    } finally {
      setExtracting(false);
    }
  }

  function validateClientSide(forSubmit) {
    const errs = {};
    if (!title.trim()) errs.title = "Title is required.";
    const numAmount = parseFloat(amount);
    if (!amount || isNaN(numAmount) || numAmount <= 0) {
      errs.amount = "Amount must be greater than zero.";
    }
    if (!expenseDate) errs.expenseDate = "Expense date is required.";
    else if (expenseDate > TODAY) errs.expenseDate = "Expense date cannot be in the future.";
    if (!category) errs.category = "Please select a category.";
    // A receipt is only required to submit for review — a draft can be saved without one yet.
    if (forSubmit && !receiptFile) {
      errs.receipt = "A receipt (JPEG, PNG, or PDF) must be attached before submitting.";
    }
    if (duplicates.length > 0 && !confirmNotDuplicate) {
      errs.duplicate = "Please confirm this isn't a duplicate before continuing.";
    }
    return errs;
  }

  async function handleSaveDraft(e) {
    e.preventDefault();
    setError("");
    const errs = validateClientSide(false);
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setBusy(true);
    try {
      const created = await api.createRequest({
        title: title.trim(),
        amount: parseFloat(amount),
        expense_date: expenseDate,
        category,
        description: description.trim() || undefined,
      });

      if (receiptFile) {
        await api.uploadReceipt(created.id, receiptFile);
      }

      setStep("done");
      setTimeout(() => router.push(`/requests/${created.id}`), 700);
    } catch (err) {
      setError(err.message || "Something went wrong while saving your draft.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveAndSubmit(e) {
    e.preventDefault();
    setError("");
    const errs = validateClientSide(true);
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setBusy(true);
    try {
      const created = await api.createRequest({
        title: title.trim(),
        amount: parseFloat(amount),
        expense_date: expenseDate,
        category,
        description: description.trim() || undefined,
      });

      await api.uploadReceipt(created.id, receiptFile);
      await api.submitRequest(created.id);

      setStep("done");
      setTimeout(() => router.push(`/requests/${created.id}`), 900);
    } catch (err) {
      setError(err.message || "Something went wrong while submitting your request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="eyebrow">Requester</div>
          <h1>New Reimbursement Request</h1>
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {step === "done" && <div className="banner banner-success">Saved. Redirecting…</div>}

      <div className="card">
        <form onSubmit={handleSaveAndSubmit}>
          <p style={{ color: "var(--ink-soft)", fontSize: "0.85rem", marginTop: 0, marginBottom: 20 }}>
            Save as a draft to finish later, or submit now if it&rsquo;s ready for review. A receipt
            is required before submitting, but not before saving a draft.
          </p>
          <div className="field">
            <label htmlFor="title">Expense title</label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Printer paper and toner"
            />
            {fieldErrors.title && <div className="field-error">{fieldErrors.title}</div>}
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="amount">Amount (USD)</label>
              <input
                id="amount"
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
              />
              {fieldErrors.amount && <div className="field-error">{fieldErrors.amount}</div>}
            </div>
            <div className="field">
              <label htmlFor="date">Expense date</label>
              <input
                id="date"
                type="date"
                max={TODAY}
                value={expenseDate}
                onChange={(e) => setExpenseDate(e.target.value)}
              />
              {fieldErrors.expenseDate && <div className="field-error">{fieldErrors.expenseDate}</div>}
            </div>
          </div>

          <div className="field">
            <label htmlFor="category">Category</label>
            <select id="category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Select a category…</option>
              <option value="travel">Travel</option>
              <option value="meals">Meals</option>
              <option value="office_supplies">Office Supplies</option>
              <option value="software_subscriptions">Software / Subscriptions</option>
              <option value="event_expenses">Event Expenses</option>
              <option value="training">Training</option>
              <option value="other">Other</option>
            </select>
            {fieldErrors.category && <div className="field-error">{fieldErrors.category}</div>}
          </div>

          <div className="field">
            <label htmlFor="description">Description / business justification</label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Why was this expense necessary?"
            />
          </div>

          <div className="field">
            <label htmlFor="receipt">Receipt (JPEG, PNG, or PDF — max 5MB, required to submit)</label>
            <input
              id="receipt"
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              onChange={(e) => handleReceiptFileChange(e.target.files?.[0] || null)}
            />
            {receiptFile && (
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginTop: 8 }}>
                {receiptPreviewUrl && (
                  <img
                    src={receiptPreviewUrl}
                    alt="Receipt preview"
                    style={{ width: 90, height: 90, objectFit: "cover", borderRadius: 4, border: "1px solid var(--line)" }}
                  />
                )}
                <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>
                  Selected: {receiptFile.name}
                  {extracting && <div style={{ marginTop: 4 }}>Reading receipt…</div>}
                </div>
              </div>
            )}
            {fieldErrors.receipt && <div className="field-error">{fieldErrors.receipt}</div>}
          </div>

          {suggestion && (suggestion.suggested_amount || suggestion.suggested_date || suggestion.suggested_merchant) && (
            <div className="card" style={{ background: "var(--paper)", marginBottom: 16 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>We read this receipt</div>
              <p style={{ fontSize: "0.78rem", color: "var(--ink-soft)", marginTop: 0, marginBottom: 10 }}>
                Automatically detected — nothing is filled in until you click one of these.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {suggestion.suggested_amount != null && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setAmount(String(suggestion.suggested_amount))}
                  >
                    Use amount: ${suggestion.suggested_amount.toFixed(2)}
                  </button>
                )}
                {suggestion.suggested_date && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setExpenseDate(suggestion.suggested_date)}
                  >
                    Use date: {suggestion.suggested_date}
                  </button>
                )}
                {suggestion.suggested_merchant && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setTitle(suggestion.suggested_merchant)}
                  >
                    Use as title: {suggestion.suggested_merchant}
                  </button>
                )}
              </div>
            </div>
          )}
          {suggestion && !suggestion.suggested_amount && !suggestion.suggested_date && !suggestion.suggested_merchant && (
            <p style={{ fontSize: "0.78rem", color: "var(--ink-soft)", marginTop: -8, marginBottom: 16 }}>
              Couldn&rsquo;t automatically read this receipt — no problem, just fill in the details manually.
            </p>
          )}

          {category && amount && parseFloat(amount) > (CATEGORY_BUDGET_LIMITS[category] || 300) && (
            <div className="banner" style={{ background: "var(--stamp-ochre-soft)", color: "var(--stamp-ochre)", border: "1px solid var(--stamp-ochre)" }}>
              This exceeds the typical budget for this category (${CATEGORY_BUDGET_LIMITS[category] || 300}).
              You can still submit it — this is just a heads-up for the reviewer.
            </div>
          )}

          {duplicates.length > 0 && (
            <div className="banner" style={{ background: "var(--stamp-ochre-soft)", color: "var(--stamp-ochre)", border: "1px solid var(--stamp-ochre)" }}>
              <strong>This looks similar to {duplicates.length === 1 ? "an existing request" : `${duplicates.length} existing requests`}:</strong>
              <ul style={{ margin: "6px 0 8px", paddingLeft: 20 }}>
                {duplicates.map((d) => (
                  <li key={d.id} style={{ fontSize: "0.85rem" }}>
                    &ldquo;{d.title}&rdquo; — {d.status}
                  </li>
                ))}
              </ul>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={confirmNotDuplicate}
                  onChange={(e) => setConfirmNotDuplicate(e.target.checked)}
                />
                This is a different expense, not a duplicate
              </label>
              {fieldErrors.duplicate && <div className="field-error">{fieldErrors.duplicate}</div>}
            </div>
          )}

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={busy} onClick={handleSaveDraft}>
              {busy ? "Saving…" : "Save as draft"}
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Submitting…" : "Submit for review"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

export default function Page() {
  return (
    <RequireAuth roles={["requester", "admin"]}>
      <NewRequestForm />
    </RequireAuth>
  );
}
