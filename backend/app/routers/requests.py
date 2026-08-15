import math
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, update

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.core.files import save_receipt
from app.models.models import (
    ReimbursementRequest, RequestHistory, Notification, User,
    StatusEnum, RoleEnum, CategoryEnum,
)
from app.schemas.schemas import (
    RequestCreate, RequestUpdate, RequestOut, RequestDetailOut, RequesterOut,
    PaginatedRequests, RejectDecision, ReviewDecision, InfoRequest, DashboardSummary,
)

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _log_history(db: Session, request_id: str, user_id: str, action: str,
                  previous_status: Optional[str], new_status: Optional[str],
                  comment: Optional[str] = None):
    entry = RequestHistory(
        request_id=request_id, user_id=user_id, action=action,
        previous_status=previous_status, new_status=new_status, comment=comment,
    )
    db.add(entry)


def _notify(db: Session, user_id: str, request_id: str, message: str):
    db.add(Notification(user_id=user_id, request_id=request_id, message=message))


def _get_owned_or_403(db: Session, request_id: str, current_user: User) -> ReimbursementRequest:
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")

    is_owner = req.requester_id == current_user.id
    is_reviewer_or_admin = current_user.role in (RoleEnum.reviewer, RoleEnum.admin)

    if not is_owner and not is_reviewer_or_admin:
        raise HTTPException(status_code=403, detail="You do not have access to this request")
    return req


def _atomic_transition(db: Session, request_id: str, allowed_from: tuple, values: dict) -> bool:
    """Conditional UPDATE (id + status match) instead of read-then-write, so two
    concurrent requests can't both pass the status check and double-submit/approve/
    pay. Returns True if this call actually made the change."""
    result = db.execute(
        update(ReimbursementRequest)
        .where(
            ReimbursementRequest.id == request_id,
            ReimbursementRequest.status.in_(allowed_from),
        )
        .values(**values)
    )
    return result.rowcount == 1


# ---------- Create / Update / Submit (Requester) ----------

@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    current_user: User = Depends(require_role(RoleEnum.requester.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    req = ReimbursementRequest(
        title=payload.title,
        amount=payload.amount,
        expense_date=payload.expense_date,
        category=payload.category,
        description=payload.description,
        status=StatusEnum.draft,
        requester_id=current_user.id,
    )
    db.add(req)
    db.flush()
    _log_history(db, req.id, current_user.id, "created", None, StatusEnum.draft.value)
    db.commit()
    db.refresh(req)
    return req


@router.patch("/{request_id}", response_model=RequestOut)
def update_draft(
    request_id: str,
    payload: RequestUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own requests")
    # a request the reviewer sent back for more info is editable too, not just drafts
    if req.status not in (StatusEnum.draft, StatusEnum.changes_requested):
        raise HTTPException(
            status_code=400,
            detail="Only draft requests or requests with changes requested can be edited",
        )

    if payload.amount is not None and payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    if payload.expense_date is not None and payload.expense_date > date.today():
        raise HTTPException(status_code=400, detail="Expense date cannot be in the future")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(req, field, value)

    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/receipt", response_model=RequestOut)
async def upload_receipt(
    request_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only attach receipts to your own requests")
    if req.status not in (StatusEnum.draft, StatusEnum.submitted, StatusEnum.under_review, StatusEnum.changes_requested):
        raise HTTPException(status_code=400, detail="Cannot change the receipt on a finalized request")

    stored_filename, stored_path = await save_receipt(file, request_id)
    req.receipt_filename = file.filename
    req.receipt_path = stored_path
    db.commit()
    db.refresh(req)
    return req


@router.get("/{request_id}/receipt")
def download_receipt(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = _get_owned_or_403(db, request_id, current_user)
    if not req.receipt_path:
        raise HTTPException(status_code=404, detail="No receipt attached to this request")
    return FileResponse(req.receipt_path, filename=req.receipt_filename)


@router.post("/{request_id}/submit", response_model=RequestOut)
def submit_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only submit your own requests")
    if not req.receipt_path:
        raise HTTPException(status_code=400, detail="A receipt must be attached before submitting")

    # for history/notification wording only, not the safety check -- that's the atomic update below
    previous = req.status.value
    was_resubmission = previous == StatusEnum.changes_requested.value

    values = {"status": StatusEnum.submitted, "submitted_at": datetime.utcnow()}
    if was_resubmission:
        values["info_requested_message"] = None

    won = _atomic_transition(
        db, request_id, (StatusEnum.draft, StatusEnum.changes_requested), values,
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=(
                "Only draft or changes-requested requests can be submitted "
                f"(current status: {current.status.value if current else 'unknown'})"
            ),
        )

    action = "resubmitted" if was_resubmission else "submitted"
    _log_history(db, request_id, current_user.id, action, previous, StatusEnum.submitted.value)
    if was_resubmission and req.reviewer_id:
        _notify(db, req.reviewer_id, request_id, f"'{req.title}' was updated and resubmitted for review.")
    db.commit()
    db.refresh(req)
    return req


# ---------- List / Detail (both roles, scoped) ----------

@router.get("", response_model=PaginatedRequests)
def list_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[CategoryEnum] = None,
    requester_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ReimbursementRequest)

    # requesters only see their own stuff, reviewers/admins see everything
    if current_user.role == RoleEnum.requester:
        query = query.filter(ReimbursementRequest.requester_id == current_user.id)
    elif requester_id:
        query = query.filter(ReimbursementRequest.requester_id == requester_id)

    if status_filter:
        # "pending" covers both submitted + under_review so a claimed request
        # doesn't disappear from the reviewer's default queue
        if status_filter == "pending":
            query = query.filter(
                ReimbursementRequest.status.in_([StatusEnum.submitted, StatusEnum.under_review])
            )
        else:
            try:
                status_enum = StatusEnum(status_filter)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"Invalid status filter: {status_filter}")
            query = query.filter(ReimbursementRequest.status == status_enum)
    if category:
        query = query.filter(ReimbursementRequest.category == category)
    if date_from:
        query = query.filter(ReimbursementRequest.expense_date >= date_from)
    if date_to:
        query = query.filter(ReimbursementRequest.expense_date <= date_to)
    if min_amount is not None:
        query = query.filter(ReimbursementRequest.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(ReimbursementRequest.amount <= max_amount)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (ReimbursementRequest.title.ilike(like)) | (ReimbursementRequest.description.ilike(like))
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = (
        query.order_by(ReimbursementRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedRequests(
        items=items, page=page, page_size=page_size, total=total, total_pages=total_pages,
    )


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = _get_owned_or_403(db, request_id, current_user)

    # reviewer opening a submitted request claims it -> under_review
    is_reviewer_or_admin = current_user.role in (RoleEnum.reviewer, RoleEnum.admin)
    is_owner = req.requester_id == current_user.id
    if is_reviewer_or_admin and not is_owner and req.status == StatusEnum.submitted:
        won = _atomic_transition(
            db, request_id, (StatusEnum.submitted,),
            {"status": StatusEnum.under_review, "reviewer_id": current_user.id},
        )
        if won:
            _log_history(
                db, request_id, current_user.id, "opened_for_review",
                StatusEnum.submitted.value, StatusEnum.under_review.value,
            )
            db.commit()
        else:
            db.rollback()
        db.refresh(req)

    return req


# ---------- Review actions (Reviewer / Admin only) ----------

@router.post("/{request_id}/approve", response_model=RequestOut)
def approve_request(
    request_id: str,
    payload: ReviewDecision,
    current_user: User = Depends(require_role(RoleEnum.reviewer.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot approve your own request")

    previous = req.status.value
    won = _atomic_transition(
        db, request_id, (StatusEnum.submitted, StatusEnum.under_review),
        {
            "status": StatusEnum.approved, "reviewer_id": current_user.id,
            "reviewer_comment": payload.comment, "reviewed_at": datetime.utcnow(),
        },
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=f"Only submitted requests can be approved (current status: {current.status.value if current else 'unknown'})",
        )

    _log_history(db, request_id, current_user.id, "approved", previous, StatusEnum.approved.value, payload.comment)
    _notify(db, req.requester_id, request_id, f"Your request '{req.title}' was approved.")
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/reject", response_model=RequestOut)
def reject_request(
    request_id: str,
    payload: RejectDecision,
    current_user: User = Depends(require_role(RoleEnum.reviewer.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot reject your own request")

    # approved-but-unpaid can still be rejected to fix a mistake; paid is final
    previous = req.status.value
    was_approved = previous == StatusEnum.approved.value
    won = _atomic_transition(
        db, request_id,
        (StatusEnum.submitted, StatusEnum.under_review, StatusEnum.changes_requested, StatusEnum.approved),
        {
            "status": StatusEnum.rejected, "reviewer_id": current_user.id,
            "rejection_reason": payload.reason, "reviewer_comment": None,
            "reviewed_at": datetime.utcnow(),
        },
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=(
                "Only submitted or approved-but-unpaid requests can be rejected "
                f"(current status: {current.status.value if current else 'unknown'})"
            ),
        )

    action = "approval_revoked" if was_approved else "rejected"
    _log_history(db, request_id, current_user.id, action, previous, StatusEnum.rejected.value, payload.reason)

    message = (
        f"Your request '{req.title}' had its approval reversed: {payload.reason}"
        if was_approved
        else f"Your request '{req.title}' was rejected: {payload.reason}"
    )
    _notify(db, req.requester_id, request_id, message)
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/request-info", response_model=RequestOut)
def request_info(
    request_id: str,
    payload: InfoRequest,
    current_user: User = Depends(require_role(RoleEnum.reviewer.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot request information on your own request")

    previous = req.status.value
    won = _atomic_transition(
        db, request_id, (StatusEnum.submitted, StatusEnum.under_review),
        {
            "status": StatusEnum.changes_requested, "reviewer_id": current_user.id,
            "info_requested_message": payload.message, "reviewed_at": datetime.utcnow(),
        },
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=(
                "Only submitted requests can have information requested "
                f"(current status: {current.status.value if current else 'unknown'})"
            ),
        )

    _log_history(db, request_id, current_user.id, "info_requested", previous, StatusEnum.changes_requested.value, payload.message)
    _notify(db, req.requester_id, request_id, f"More information was requested on '{req.title}': {payload.message}")
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/mark-paid", response_model=RequestOut)
def mark_paid(
    request_id: str,
    current_user: User = Depends(require_role(RoleEnum.reviewer.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id == current_user.id:
        raise HTTPException(status_code=403, detail="You cannot mark your own request as paid")

    previous = req.status.value
    # highest stakes of these -- a race here means double payment
    won = _atomic_transition(
        db, request_id, (StatusEnum.approved,),
        {"status": StatusEnum.paid, "paid_at": datetime.utcnow()},
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=f"Only approved requests can be marked as paid (current status: {current.status.value if current else 'unknown'})",
        )

    _log_history(db, request_id, current_user.id, "marked_paid", previous, StatusEnum.paid.value)
    _notify(db, req.requester_id, request_id, f"Your request '{req.title}' has been paid.")
    db.commit()
    db.refresh(req)
    return req


# ---------- Dashboard ----------

@router.get("/meta/requesters", response_model=list[RequesterOut])
def list_requesters(
    current_user: User = Depends(require_role(RoleEnum.reviewer.value, RoleEnum.admin.value)),
    db: Session = Depends(get_db),
):
    """Distinct list of requesters, for populating the 'Requester' filter on
    the reviewer dashboard. Reviewers can't hit the admin-only /api/admin/users
    endpoint, so this gives them just enough to filter by without exposing
    full account management."""
    return (
        db.query(User)
        .filter(User.role == RoleEnum.requester)
        .order_by(User.name)
        .all()
    )


@router.get("/stats/dashboard", response_model=DashboardSummary)
def dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ReimbursementRequest)
    if current_user.role == RoleEnum.requester:
        query = query.filter(ReimbursementRequest.requester_id == current_user.id)

    all_requests = query.all()

    total_requested = sum(r.amount for r in all_requests if r.status != StatusEnum.draft)
    total_approved = sum(r.amount for r in all_requests if r.status in (StatusEnum.approved, StatusEnum.paid))
    # "pending" = awaiting reviewer action, so changes_requested doesn't count here
    total_pending = sum(r.amount for r in all_requests if r.status in (StatusEnum.submitted, StatusEnum.under_review))
    total_paid = sum(r.amount for r in all_requests if r.status == StatusEnum.paid)

    count_by_status = {s.value: 0 for s in StatusEnum}
    for r in all_requests:
        count_by_status[r.status.value] += 1

    return DashboardSummary(
        total_requested=total_requested,
        total_approved=total_approved,
        total_pending=total_pending,
        total_paid=total_paid,
        count_by_status=count_by_status,
    )
