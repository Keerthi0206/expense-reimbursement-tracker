import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, DateTime, Date, Enum, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    requester = "requester"
    reviewer = "reviewer"
    admin = "admin"


class StatusEnum(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    paid = "paid"
    cancelled = "cancelled"


class CategoryEnum(str, enum.Enum):
    travel = "travel"
    meals = "meals"
    office_supplies = "office_supplies"
    software_subscriptions = "software_subscriptions"
    event_expenses = "event_expenses"
    training = "training"
    other = "other"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.requester)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    requests = relationship(
        "ReimbursementRequest",
        back_populates="requester",
        foreign_keys="ReimbursementRequest.requester_id",
    )


class ReimbursementRequest(Base):
    __tablename__ = "reimbursement_requests"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    expense_date = Column(Date, nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.draft)

    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    reviewer_id = Column(String, ForeignKey("users.id"), nullable=True)

    receipt_filename = Column(String, nullable=True)
    receipt_path = Column(String, nullable=True)

    rejection_reason = Column(Text, nullable=True)
    reviewer_comment = Column(Text, nullable=True)
    info_requested_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    requester = relationship(
        "User", back_populates="requests", foreign_keys=[requester_id]
    )
    history = relationship(
        "RequestHistory", back_populates="request", cascade="all, delete-orphan",
        order_by="RequestHistory.timestamp",
    )


class RequestHistory(Base):
    __tablename__ = "request_history"

    id = Column(String, primary_key=True, default=gen_uuid)
    request_id = Column(String, ForeignKey("reimbursement_requests.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    request = relationship("ReimbursementRequest", back_populates="history")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    request_id = Column(String, ForeignKey("reimbursement_requests.id"), nullable=True)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserAccountHistory(Base):
    """Audit trail for admin actions on a user account: role changes and
    activate/deactivate events. Separate from RequestHistory, which tracks
    reimbursement-request workflow actions, not account administration."""

    __tablename__ = "user_account_history"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)  # the account that was changed
    performed_by_id = Column(String, ForeignKey("users.id"), nullable=False)  # the admin who did it
    action = Column(String, nullable=False)  # "created" | "role_changed" | "activated" | "deactivated"
    previous_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
