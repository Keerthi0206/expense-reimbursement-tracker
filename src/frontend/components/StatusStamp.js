const LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  under_review: "Under Review",
  changes_requested: "Changes Requested",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
};

export default function StatusStamp({ status }) {
  return <span className={`stamp stamp-${status}`}>{LABELS[status] || status}</span>;
}

export function statusLabel(status) {
  return LABELS[status] || status;
}
