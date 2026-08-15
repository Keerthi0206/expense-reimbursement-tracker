from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role, hash_password
from app.models.models import User, RoleEnum, UserAccountHistory
from app.schemas.schemas import (
    UserOut, UserCreate, UserRoleUpdate, UserStatusUpdate, UserDetailOut, UserAccountHistoryOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _log_account_history(db: Session, user_id: str, performed_by_id: str, action: str,
                          previous_value: str = None, new_value: str = None):
    db.add(UserAccountHistory(
        user_id=user_id, performed_by_id=performed_by_id, action=action,
        previous_value=previous_value, new_value=new_value,
    ))


@router.get("/users", response_model=list[UserOut])
def list_users(
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.created_at.desc()).all()


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


@router.get("/users/{user_id}/history", response_model=list[UserAccountHistoryOut])
def get_user_history(
    user_id: str,
    current_user: User = Depends(require_role(RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return (
        db.query(UserAccountHistory)
        .filter(UserAccountHistory.user_id == user_id)
        .order_by(UserAccountHistory.timestamp.desc())
        .all()
    )


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
    _log_account_history(db, user.id, current_user.id, "role_changed", previous_role, payload.role.value)
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
        _log_account_history(db, user.id, current_user.id, action, previous_status, new_status)
    db.commit()
    db.refresh(user)
    return user
