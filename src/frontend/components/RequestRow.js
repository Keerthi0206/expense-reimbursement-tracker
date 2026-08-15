import Link from "next/link";
import StatusStamp from "./StatusStamp";

const CATEGORY_LABELS = {
  travel: "Travel",
  meals: "Meals",
  office_supplies: "Office Supplies",
  software_subscriptions: "Software / Subscriptions",
  event_expenses: "Event Expenses",
  training: "Training",
  other: "Other",
};

function daysWaiting(submittedAt) {
  if (!submittedAt) return null;
  const days = Math.floor((Date.now() - new Date(submittedAt).getTime()) / (1000 * 60 * 60 * 24));
  return days;
}

export default function RequestRow({ request, showRequester = false }) {
  const waiting = daysWaiting(request.submitted_at);
  const isPending = request.status === "submitted" || request.status === "under_review";

  return (
    <Link href={`/requests/${request.id}`} className={`ledger-row stripe-${request.status}`}>
      <div className="ledger-main">
        <div className="ledger-title">{request.title}</div>
        <div className="ledger-meta">
          {CATEGORY_LABELS[request.category] || request.category} · {request.expense_date}
          {showRequester && request.requester ? ` · ${request.requester.name}` : ""}
          {isPending && waiting !== null ? ` · waiting ${waiting}d` : ""}
        </div>
      </div>
      <div className="ledger-amount mono">${request.amount.toFixed(2)}</div>
      <StatusStamp status={request.status} />
    </Link>
  );
}

export { CATEGORY_LABELS };
