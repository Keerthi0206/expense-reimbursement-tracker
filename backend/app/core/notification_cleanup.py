"""
Deletes notifications that are both read AND older than
NOTIFICATION_RETENTION_DAYS. Unread notifications are never touched,
regardless of age -- only ones the person has already seen and dismissed
are eligible for cleanup. Prevents the notifications table from growing
without bound in a long-running deployment.
"""
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import Notification

NOTIFICATION_RETENTION_DAYS = int(os.getenv("NOTIFICATION_RETENTION_DAYS", "90"))


def cleanup_old_notifications(db: Session) -> int:
    cutoff = datetime.utcnow() - timedelta(days=NOTIFICATION_RETENTION_DAYS)
    deleted = (
        db.query(Notification)
        .filter(Notification.is_read == True, Notification.created_at <= cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
