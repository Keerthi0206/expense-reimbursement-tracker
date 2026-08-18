from typing import Optional

import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role, hash_password
from app.core.reminders import send_pending_reminders, REMINDER_THRESHOLD_DAYS
from app.models.models import User, RoleEnum, UserAccountHistory
from app.schemas.schemas import (
    UserOut, UserCreate, UserRoleUpdate, UserStatusUpdate, UserDetailOut,
    PaginatedUsers, PaginatedUserHistory,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _log_account_history(db: Session, user_id: str, performed_by_id: str, action: str,
                          previous_value: str = None, new_value: str = None, reason: str = None):
    db.add(UserAccountHistory(
        user_id=user_id, performed_by_id=performed_by_id, action=action,
        previous_value=previous_value, new_value=new_value, reason=reason,
    ))


@router.get("/users", response_model=PaginatedUsers)
def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|name|email|role)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    query = db.query(User)

    if role:
        try:
            role_enum = RoleEnum(role)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid role filter: {role}")
        query = query.filter(User.role == role_enum)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        like = f"%{search}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)))

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))

    sort_column = getattr(User, sort_by)
    sort_expr = sort_column.asc() if order == "asc" else sort_column.desc()

    items = query.order_by(sort_expr).offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedUsers(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@router.get("/users/{user_id}", response_model=UserDetailOut)
def get_user(
    user_id: str,
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}/history", response_model=PaginatedUserHistory)
def get_user_history(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    query = db.query(UserAccountHistory).filter(UserAccountHistory.user_id == user_id)
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = (
        query.order_by(UserAccountHistory.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedUserHistory(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()
    _log_account_history(db, user.id, current_user.id, "created", None, payload.role.value)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserOut)
def update_role(
    user_id: str,
    payload: UserRoleUpdate,
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    previous_role = user.role.value
    user.role = payload.role
    _log_account_history(
        db, user.id, current_user.id, "role_changed", previous_role, payload.role.value, payload.reason,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/status", response_model=UserOut)
def update_status(
    user_id: str,
    payload: UserStatusUpdate,
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    previous_status = "active" if user.is_active else "inactive"
    new_status = "active" if payload.is_active else "inactive"
    user.is_active = payload.is_active
    if previous_status != new_status:
        action = "activated" if payload.is_active else "deactivated"
        _log_account_history(db, user.id, current_user.id, action, previous_status, new_status, payload.reason)
    db.commit()
    db.refresh(user)
    return user


@router.post("/trigger-reminders")
def trigger_reminders(
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    """Manually runs the same reminder check the background scheduler runs
    periodically. Exists so reminders are actually testable/demoable without
    waiting REMINDER_THRESHOLD_DAYS of real wall-clock time."""
    count = send_pending_reminders(db)
    return {"reminders_sent": count, "threshold_days": REMINDER_THRESHOLD_DAYS}
