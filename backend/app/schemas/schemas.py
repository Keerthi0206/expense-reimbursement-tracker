from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.models import RoleEnum, StatusEnum, CategoryEnum


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------- Users ----------

class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: RoleEnum
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: RoleEnum = RoleEnum.requester


class UserRoleUpdate(BaseModel):
    role: RoleEnum
    reason: Optional[str] = None


class UserStatusUpdate(BaseModel):
    is_active: bool
    reason: Optional[str] = None


class UserAccountHistoryOut(BaseModel):
    id: str
    user_id: str
    performed_by_id: str
    action: str
    previous_value: Optional[str]
    new_value: Optional[str]
    reason: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class UserDetailOut(UserOut):
    history: List[UserAccountHistoryOut] = []


# ---------- Reimbursement Requests ----------

class RequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    amount: float
    expense_date: date
    category: CategoryEnum
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v

    @field_validator("expense_date")
    @classmethod
    def date_not_in_future(cls, v):
        if v > date.today():
            raise ValueError("Expense date cannot be in the future")
        return v


class RequestUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None
    expense_date: Optional[date] = None
    category: Optional[CategoryEnum] = None
    description: Optional[str] = None


class ReviewDecision(BaseModel):
    comment: Optional[str] = None


class RejectDecision(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class InfoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class CancelRequest(BaseModel):
    reason: Optional[str] = None


class RequesterOut(BaseModel):
    id: str
    name: str
    email: str

    class Config:
        from_attributes = True


class HistoryEntryOut(BaseModel):
    id: str
    user_id: str
    action: str
    previous_status: Optional[str]
    new_status: Optional[str]
    comment: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class RequestOut(BaseModel):
    id: str
    title: str
    amount: float
    expense_date: date
    category: CategoryEnum
    description: Optional[str]
    status: StatusEnum
    requester: RequesterOut
    receipt_filename: Optional[str]
    rejection_reason: Optional[str]
    reviewer_comment: Optional[str]
    info_requested_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    paid_at: Optional[datetime]

    class Config:
        from_attributes = True


class RequestDetailOut(RequestOut):
    history: List[HistoryEntryOut] = []


class PaginatedRequests(BaseModel):
    items: List[RequestOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedUsers(BaseModel):
    items: List[UserOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class NotificationOut(BaseModel):
    id: str
    message: str
    is_read: bool
    request_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedNotifications(BaseModel):
    items: List[NotificationOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedHistory(BaseModel):
    items: List[HistoryEntryOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedUserHistory(BaseModel):
    items: List[UserAccountHistoryOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class DashboardSummary(BaseModel):
    total_requested: float
    total_approved: float
    total_pending: float
    total_paid: float
    count_by_status: dict
