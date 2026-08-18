const LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  under_review: "Under Review",
  changes_requested: "Changes Requested",
  pending_second_approval: "Pending 2nd Approval",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
  cancelled: "Cancelled",
};

export default function StatusStamp({ status }) {
  return <span className={`stamp stamp-${status}`}>{LABELS[status] || status}</span>;
}

export function statusLabel(status) {
  return LABELS[status] || status;
}
