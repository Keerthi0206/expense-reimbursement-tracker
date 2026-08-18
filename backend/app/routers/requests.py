import math
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.core.files import save_receipt, _detect_type, MAX_FILE_SIZE
from app.core.workflow_rules import requires_second_approval
from app.core.receipt_extraction import extract_receipt_suggestions, get_file_metadata
from app.core.analytics import (
    compute_monthly_totals, compute_by_category, compute_by_requester,
    compute_approval_time, compute_reviewer_workload, compute_average_request_amount,
)
from app.models.models import (
    ReimbursementRequest, RequestHistory, Notification, User,
    StatusEnum, RoleEnum, CategoryEnum,
)
from app.schemas.schemas import (
    RequestCreate, RequestUpdate, RequestOut, RequestDetailOut, RequesterOut,
    PaginatedRequests, RejectDecision, ReviewDecision, InfoRequest, CancelRequest,
    DashboardSummary, PaginatedHistory, DuplicateCandidateOut,
    ReceiptSuggestionOut, ReceiptAnalysisOut, AnalyticsOut,
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
    # a request the reviewer sent back for more info, or that was rejected, is editable too
    if req.status not in (StatusEnum.draft, StatusEnum.changes_requested, StatusEnum.rejected):
        raise HTTPException(
            status_code=400,
            detail="Only draft, changes-requested, or rejected requests can be edited",
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
    if req.status not in (
        StatusEnum.draft, StatusEnum.submitted, StatusEnum.under_review,
        StatusEnum.changes_requested, StatusEnum.rejected,
    ):
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
    was_resubmission = previous in (StatusEnum.changes_requested.value, StatusEnum.rejected.value)

    values = {"status": StatusEnum.submitted, "submitted_at": datetime.utcnow()}
    if was_resubmission:
        values["info_requested_message"] = None
        values["rejection_reason"] = None

    won = _atomic_transition(
        db, request_id, (StatusEnum.draft, StatusEnum.changes_requested, StatusEnum.rejected), values,
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=(
                "Only draft, rejected, or changes-requested requests can be submitted "
                f"(current status: {current.status.value if current else 'unknown'})"
            ),
        )

    action = "resubmitted" if was_resubmission else "submitted"
    _log_history(db, request_id, current_user.id, action, previous, StatusEnum.submitted.value)
    if was_resubmission and req.reviewer_id:
        _notify(db, req.reviewer_id, request_id, f"'{req.title}' was updated and resubmitted for review.")
    elif not was_resubmission:
        # No specific reviewer is assigned yet on a fresh submission, so let
        # every active reviewer/admin know something new needs attention.
        reviewers = db.query(User).filter(
            User.role.in_([RoleEnum.reviewer, RoleEnum.admin]), User.is_active == True,
        ).all()
        for reviewer in reviewers:
            _notify(db, reviewer.id, request_id, f"New request '{req.title}' was submitted for review.")
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/cancel", response_model=RequestOut)
def cancel_request(
    request_id: str,
    payload: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Reimbursement request not found")
    if req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own requests")

    previous = req.status.value
    won = _atomic_transition(
        db, request_id,
        (StatusEnum.draft, StatusEnum.submitted, StatusEnum.under_review, StatusEnum.changes_requested),
        {"status": StatusEnum.cancelled},
    )
    if not won:
        db.rollback()
        current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
        raise HTTPException(
            status_code=400,
            detail=(
                "Only requests that haven't been approved, rejected, or paid can be cancelled "
                f"(current status: {current.status.value if current else 'unknown'})"
            ),
        )

    _log_history(db, request_id, current_user.id, "cancelled", previous, StatusEnum.cancelled.value, payload.reason)
    if req.reviewer_id:
        message = f"'{req.title}' was cancelled by the requester."
        if payload.reason:
            message += f" Reason: {payload.reason}"
        _notify(db, req.reviewer_id, request_id, message)
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
    sort_by: str = Query("created_at", pattern="^(created_at|amount|expense_date|status|title)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
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

    sort_column = getattr(ReimbursementRequest, sort_by)
    sort_expr = sort_column.asc() if order == "asc" else sort_column.desc()

    items = (
        query.order_by(sort_expr)
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
            _notify(db, req.requester_id, request_id, f"Your request '{req.title}' is now under review.")
            db.commit()
        else:
            db.rollback()
        db.refresh(req)

    return req


@router.get("/{request_id}/history", response_model=PaginatedHistory)
def get_request_history(
    request_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_or_403(db, request_id, current_user)
    query = db.query(RequestHistory).filter(RequestHistory.request_id == request_id)
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = (
        query.order_by(RequestHistory.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedHistory(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


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

    if req.status in (StatusEnum.submitted, StatusEnum.under_review):
        # First-tier approval. Some requests need a second, admin-level
        # sign-off before they're actually approved -- see core/workflow_rules.py.
        if requires_second_approval(req.category.value, req.amount):
            won = _atomic_transition(
                db, request_id, (StatusEnum.submitted, StatusEnum.under_review),
                {
                    "status": StatusEnum.pending_second_approval, "reviewer_id": current_user.id,
                    "first_approver_id": current_user.id, "reviewer_comment": payload.comment,
                    "reviewed_at": datetime.utcnow(),
                },
            )
            if not won:
                db.rollback()
                current = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
                raise HTTPException(
                    status_code=400,
                    detail=f"Only submitted requests can be approved (current status: {current.status.value if current else 'unknown'})",
                )
            _log_history(db, request_id, current_user.id, "first_approval_given",
                         previous, StatusEnum.pending_second_approval.value, payload.comment)
            admins = db.query(User).filter(User.role == RoleEnum.admin, User.is_active == True).all()
            for admin_user in admins:
                if admin_user.id != current_user.id:
                    _notify(db, admin_user.id, request_id,
                            f"'{req.title}' needs a second approval (exceeds the normal threshold or is a training expense).")
            db.commit()
            db.refresh(req)
            return req

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

    if req.status == StatusEnum.pending_second_approval:
        if current_user.role != RoleEnum.admin:
            raise HTTPException(status_code=403, detail="The second approval must come from an admin")
        if req.first_approver_id == current_user.id:
            raise HTTPException(status_code=403, detail="The second approval must come from a different person than the first")

        won = _atomic_transition(
            db, request_id, (StatusEnum.pending_second_approval,),
            {
                "status": StatusEnum.approved, "reviewer_id": current_user.id,
                "reviewer_comment": payload.comment, "reviewed_at": datetime.utcnow(),
            },
        )
        if not won:
            db.rollback()
            raise HTTPException(status_code=400, detail="This request is no longer awaiting second approval")
        _log_history(db, request_id, current_user.id, "second_approval_given",
                     previous, StatusEnum.approved.value, payload.comment)
        _notify(db, req.requester_id, request_id, f"Your request '{req.title}' was approved.")
        db.commit()
        db.refresh(req)
        return req

    raise HTTPException(
        status_code=400,
        detail=f"Only submitted requests can be approved (current status: {req.status.value})",
    )


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
        (
            StatusEnum.submitted, StatusEnum.under_review, StatusEnum.changes_requested,
            StatusEnum.pending_second_approval, StatusEnum.approved,
        ),
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


@router.get("/meta/check-duplicate", response_model=list[DuplicateCandidateOut])
def check_duplicate(
    amount: float,
    expense_date: date,
    exclude_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Surfaces the requester's own existing requests with the same amount and
    expense date, so the frontend can warn before creating a likely-duplicate
    request. This is a warning, not a block -- two genuinely different expenses
    can share an amount and date, so the requester decides whether to proceed.
    Cancelled/rejected requests are excluded since they're dead ends, not live
    duplicates."""
    query = db.query(ReimbursementRequest).filter(
        ReimbursementRequest.requester_id == current_user.id,
        ReimbursementRequest.amount == amount,
        ReimbursementRequest.expense_date == expense_date,
        ReimbursementRequest.status.notin_([StatusEnum.cancelled, StatusEnum.rejected]),
    )
    if exclude_id:
        query = query.filter(ReimbursementRequest.id != exclude_id)
    return query.order_by(ReimbursementRequest.created_at.desc()).all()


@router.post("/meta/extract-receipt", response_model=ReceiptSuggestionOut)
async def extract_receipt_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Runs OCR/parsing on a receipt BEFORE a request exists, so the New
    Request form can suggest amount/date/merchant while the requester is
    still filling it out. Nothing here is persisted -- the file still has
    to go through the normal upload-receipt endpoint once the request is
    actually created. These are suggestions only; the frontend must let the
    requester review and apply them, never auto-fill silently."""
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Receipt file exceeds the 5 MB size limit")
    mime, _ = _detect_type(contents[:16])
    if mime is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only JPEG, PNG, and PDF receipts are accepted.",
        )
    suggestion = extract_receipt_suggestions(contents, mime)
    return suggestion


@router.get("/{request_id}/receipt-analysis", response_model=ReceiptAnalysisOut)
def get_receipt_analysis(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-runs OCR against a request's ALREADY-STORED receipt and compares
    it to what was actually submitted -- the receipt/request consistency
    check. On-demand only (not run automatically on every list/detail
    fetch), since OCR is real work, not free like the budget-limit computed
    fields. Available to the owner or any reviewer/admin, same as viewing
    the request itself."""
    req = _get_owned_or_403(db, request_id, current_user)
    if not req.receipt_path or not os.path.exists(req.receipt_path):
        raise HTTPException(status_code=400, detail="This request has no receipt attached yet")

    with open(req.receipt_path, "rb") as f:
        contents = f.read()
    mime, _ = _detect_type(contents[:16])
    if mime is None:
        raise HTTPException(status_code=500, detail="Stored receipt file is not a recognized type")

    metadata = get_file_metadata(contents, mime)
    suggestion = extract_receipt_suggestions(contents, mime)

    amount_mismatch = (
        suggestion["suggested_amount"] is not None
        and abs(suggestion["suggested_amount"] - req.amount) > 0.01
    )
    date_mismatch = (
        suggestion["suggested_date"] is not None
        and suggestion["suggested_date"] != req.expense_date.isoformat()
    )

    return ReceiptAnalysisOut(
        metadata=metadata,
        suggestion=suggestion,
        amount_mismatch=amount_mismatch,
        date_mismatch=date_mismatch,
        submitted_amount=req.amount,
        submitted_date=req.expense_date,
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

    total_requested = sum(
        r.amount for r in all_requests if r.status not in (StatusEnum.draft, StatusEnum.cancelled)
    )
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


@router.get("/stats/analytics", response_model=AnalyticsOut)
def analytics(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requesters get their own monthly/category breakdown and average
    request size. Reviewers/admins get the same plus the cross-user views
    (by_requester, reviewer_workload) that only make sense at that level.
    date_from/date_to optionally scope everything to a specific window
    (e.g. one month) -- unfiltered by default, showing all-time data."""
    query = db.query(ReimbursementRequest)
    if current_user.role == RoleEnum.requester:
        query = query.filter(ReimbursementRequest.requester_id == current_user.id)
    if date_from:
        query = query.filter(ReimbursementRequest.expense_date >= date_from)
    if date_to:
        query = query.filter(ReimbursementRequest.expense_date <= date_to)
    all_requests = query.all()

    is_reviewer_or_admin = current_user.role in (RoleEnum.reviewer, RoleEnum.admin)

    return AnalyticsOut(
        monthly_totals=compute_monthly_totals(all_requests),
        by_category=compute_by_category(all_requests),
        by_requester=compute_by_requester(all_requests) if is_reviewer_or_admin else [],
        approval_time=compute_approval_time(all_requests),
        reviewer_workload=compute_reviewer_workload(all_requests) if is_reviewer_or_admin else [],
        average_request_amount=compute_average_request_amount(all_requests),
    )


def _scoped_export_query(current_user: User, db: Session, status_filter: Optional[str],
                          category_filter: Optional[str], date_from: Optional[date], date_to: Optional[date]):
    query = db.query(ReimbursementRequest)
    if current_user.role == RoleEnum.requester:
        query = query.filter(ReimbursementRequest.requester_id == current_user.id)
    if status_filter:
        query = query.filter(ReimbursementRequest.status == status_filter)
    if category_filter:
        query = query.filter(ReimbursementRequest.category == category_filter)
    if date_from:
        query = query.filter(ReimbursementRequest.expense_date >= date_from)
    if date_to:
        query = query.filter(ReimbursementRequest.expense_date <= date_to)
    return query.order_by(ReimbursementRequest.expense_date.desc())


@router.get("/export/csv")
def export_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    requests_list = _scoped_export_query(current_user, db, status_filter, category, date_from, date_to).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Title", "Amount", "Category", "Expense Date", "Status", "Requester", "Requester Email",
        "Submitted At", "Reviewed At", "Paid At",
    ])
    for r in requests_list:
        writer.writerow([
            r.title, f"{r.amount:.2f}", r.category.value, r.expense_date.isoformat(), r.status.value,
            r.requester.name, r.requester.email,
            r.submitted_at.isoformat() if r.submitted_at else "",
            r.reviewed_at.isoformat() if r.reviewed_at else "",
            r.paid_at.isoformat() if r.paid_at else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expense_requests.csv"},
    )


@router.get("/export/pdf")
def export_pdf(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import io
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    requests_list = _scoped_export_query(current_user, db, status_filter, category, date_from, date_to).all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Expense Report")
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("CDF Expense & Reimbursement Report", styles["Title"]),
        Paragraph(f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} by {current_user.name}", styles["Normal"]),
        Spacer(1, 16),
    ]

    total = sum(r.amount for r in requests_list)
    elements.append(Paragraph(f"{len(requests_list)} request(s), totaling ${total:,.2f}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    table_data = [["Title", "Amount", "Category", "Date", "Status", "Requester"]]
    for r in requests_list:
        table_data.append([
            r.title[:30], f"${r.amount:,.2f}", r.category.value.replace("_", " "),
            r.expense_date.isoformat(), r.status.value.replace("_", " "), r.requester.name,
        ])

    table = Table(table_data, repeatRows=1, colWidths=[1.6 * inch, 0.8 * inch, 1.1 * inch, 0.9 * inch, 1.0 * inch, 1.1 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17241d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f4")]),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=expense_report.pdf"},
    )
