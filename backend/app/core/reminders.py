"""
Sends a reminder notification to active reviewers/admins for any request
that's been sitting in submitted/under_review for too long without a
decision. Called periodically by the scheduler in main.py, and also
exposed via a manual-trigger endpoint for testing/demo purposes -- waiting
real days for the scheduler to fire isn't practical to verify by hand.

At most one reminder per request per REMINDER_THRESHOLD_DAYS window, via
last_reminder_sent_at, so this doesn't spam reviewers on every scheduler run.
"""
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import ReimbursementRequest, RoleEnum, StatusEnum, User
from app.routers.requests import _notify

REMINDER_THRESHOLD_DAYS = int(os.getenv("REMINDER_THRESHOLD_DAYS", "3"))


def send_pending_reminders(db: Session) -> int:
    cutoff = datetime.utcnow() - timedelta(days=REMINDER_THRESHOLD_DAYS)

    stale_requests = (
        db.query(ReimbursementRequest)
        .filter(
            ReimbursementRequest.status.in_([StatusEnum.submitted, StatusEnum.under_review]),
            ReimbursementRequest.submitted_at.isnot(None),
            ReimbursementRequest.submitted_at <= cutoff,
        )
        .filter(
            (ReimbursementRequest.last_reminder_sent_at.is_(None))
            | (ReimbursementRequest.last_reminder_sent_at <= cutoff)
        )
        .all()
    )

    if not stale_requests:
        return 0

    active_reviewers = (
        db.query(User)
        .filter(User.role.in_([RoleEnum.reviewer, RoleEnum.admin]), User.is_active == True)
        .all()
    )

    for req in stale_requests:
        days_waiting = (datetime.utcnow() - req.submitted_at).days
        message = f"'{req.title}' has been waiting {days_waiting} days for review."
        recipients = [req.reviewer_id] if req.reviewer_id else [u.id for u in active_reviewers]
        for user_id in recipients:
            _notify(db, user_id, req.id, message)
        req.last_reminder_sent_at = datetime.utcnow()

    db.commit()
    return len(stale_requests)
