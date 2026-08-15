"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import RequireAuth from "../../../lib/require-auth";
import { api } from "../../../lib/api";

const TODAY = new Date().toISOString().slice(0, 10);

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
              onChange={(e) => setReceiptFile(e.target.files?.[0] || null)}
            />
            {receiptFile && <div style={{ fontSize: "0.82rem", color: "var(--ink-soft)", marginTop: 4 }}>Selected: {receiptFile.name}</div>}
            {fieldErrors.receipt && <div className="field-error">{fieldErrors.receipt}</div>}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
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
