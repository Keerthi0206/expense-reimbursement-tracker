"""
Reporting/analytics computations, kept separate from the requests router
since this is genuinely a different concern (aggregation, not workflow).
Requester-scoped by the caller (see the /stats/analytics endpoint) --
this module just crunches whatever list of requests it's handed.
"""
import statistics
from collections import defaultdict

from app.models.models import StatusEnum


def _billable_requests(requests):
    """Requests that represent a real spend figure -- excludes drafts
    (never finalized) and cancelled (withdrawn, never happened)."""
    return [r for r in requests if r.status not in (StatusEnum.draft, StatusEnum.cancelled)]


def compute_monthly_totals(requests) -> list[dict]:
    billable = _billable_requests(requests)
    buckets = defaultdict(lambda: {"total": 0.0, "count": 0})
    for r in billable:
        key = r.expense_date.strftime("%Y-%m")
        buckets[key]["total"] += r.amount
        buckets[key]["count"] += 1
    return [
        {"month": month, "total": round(data["total"], 2), "count": data["count"]}
        for month, data in sorted(buckets.items())
    ]


def compute_by_category(requests) -> list[dict]:
    billable = _billable_requests(requests)
    buckets = defaultdict(lambda: {"total": 0.0, "count": 0})
    for r in billable:
        key = r.category.value
        buckets[key]["total"] += r.amount
        buckets[key]["count"] += 1
    return [
        {"category": cat, "total": round(data["total"], 2), "count": data["count"]}
        for cat, data in sorted(buckets.items(), key=lambda kv: -kv[1]["total"])
    ]


def compute_by_requester(requests) -> list[dict]:
    billable = _billable_requests(requests)
    buckets = defaultdict(lambda: {"total": 0.0, "count": 0, "name": ""})
    for r in billable:
        key = r.requester_id
        buckets[key]["total"] += r.amount
        buckets[key]["count"] += 1
        buckets[key]["name"] = r.requester.name
    return [
        {"requester_id": rid, "requester_name": data["name"],
         "total": round(data["total"], 2), "count": data["count"]}
        for rid, data in sorted(buckets.items(), key=lambda kv: -kv[1]["total"])
    ]


def compute_approval_time(requests) -> dict:
    """Days from submission to the review decision, for requests that
    actually reached a decision (approved, rejected, or paid)."""
    days = []
    for r in requests:
        if r.status in (StatusEnum.approved, StatusEnum.rejected, StatusEnum.paid) and r.submitted_at and r.reviewed_at:
            delta = (r.reviewed_at - r.submitted_at).total_seconds() / 86400
            days.append(delta)
    if not days:
        return {"avg_days": None, "median_days": None, "count": 0}
    return {
        "avg_days": round(statistics.mean(days), 1),
        "median_days": round(statistics.median(days), 1),
        "count": len(days),
    }


def compute_reviewer_workload(requests) -> list[dict]:
    buckets = defaultdict(lambda: {"approved": 0, "rejected": 0, "name": ""})
    for r in requests:
        if r.status in (StatusEnum.approved, StatusEnum.paid) and r.reviewer_id:
            buckets[r.reviewer_id]["approved"] += 1
            buckets[r.reviewer_id]["name"] = r.reviewer.name if r.reviewer else ""
        elif r.status == StatusEnum.rejected and r.reviewer_id:
            buckets[r.reviewer_id]["rejected"] += 1
            buckets[r.reviewer_id]["name"] = r.reviewer.name if r.reviewer else ""
    return [
        {
            "reviewer_id": rid, "reviewer_name": data["name"],
            "approved_count": data["approved"], "rejected_count": data["rejected"],
            "total_reviewed": data["approved"] + data["rejected"],
        }
        for rid, data in sorted(buckets.items(), key=lambda kv: -(kv[1]["approved"] + kv[1]["rejected"]))
    ]


def compute_average_request_amount(requests) -> float:
    billable = _billable_requests(requests)
    if not billable:
        return 0.0
    return round(sum(r.amount for r in billable) / len(billable), 2)
