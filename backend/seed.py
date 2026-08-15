"""
Seeds the database with demo accounts and fictional sample reimbursement
requests covering every workflow state, for demo/testing purposes.

Run with: python seed.py
"""
from datetime import date, timedelta

from app.core.database import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models.models import (
    User, ReimbursementRequest, RequestHistory, RoleEnum, StatusEnum, CategoryEnum,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

if db.query(User).count() > 0:
    print("Database already has data. Skipping seed. Delete expense_tracker.db to reseed.")
    db.close()
    raise SystemExit(0)

# ---- Demo accounts ----
alice = User(name="Alice Requester", email="alice@example.com",
             hashed_password=hash_password("password123"), role=RoleEnum.requester)
bob = User(name="Bob Requester", email="bob@example.com",
           hashed_password=hash_password("password123"), role=RoleEnum.requester)
rachel = User(name="Rachel Reviewer", email="rachel@example.com",
              hashed_password=hash_password("password123"), role=RoleEnum.reviewer)
admin = User(name="Admin User", email="admin@example.com",
             hashed_password=hash_password("password123"), role=RoleEnum.admin)

db.add_all([alice, bob, rachel, admin])
db.flush()

today = date.today()


def make_request(**kwargs):
    req = ReimbursementRequest(**kwargs)
    db.add(req)
    db.flush()
    return req


# 1. Valid office-supply reimbursement (submitted, awaiting review)
r1 = make_request(
    title="Printer paper and toner", amount=84.50, expense_date=today - timedelta(days=2),
    category=CategoryEnum.office_supplies, description="Restocking office supplies for the volunteer center.",
    status=StatusEnum.submitted, requester_id=alice.id,
    receipt_filename="office_supplies_receipt.pdf", receipt_path=None,
    submitted_at=today - timedelta(days=2),
)
db.add(RequestHistory(request_id=r1.id, user_id=alice.id, action="created",
                       previous_status=None, new_status="draft"))
db.add(RequestHistory(request_id=r1.id, user_id=alice.id, action="submitted",
                       previous_status="draft", new_status="submitted"))

# 2. Travel request missing a receipt (still draft, blocked from submitting)
r2 = make_request(
    title="Conference travel - Chicago", amount=412.00, expense_date=today - timedelta(days=5),
    category=CategoryEnum.travel, description="Round-trip flight for the nonprofit tech summit.",
    status=StatusEnum.draft, requester_id=bob.id,
)
db.add(RequestHistory(request_id=r2.id, user_id=bob.id, action="created",
                       previous_status=None, new_status="draft"))

# 3. Meal request with a since-corrected amount (kept in draft to illustrate validation)
r3 = make_request(
    title="Team lunch - volunteer appreciation", amount=63.25, expense_date=today - timedelta(days=1),
    category=CategoryEnum.meals, description="Lunch for 6 volunteers after the weekend build day.",
    status=StatusEnum.draft, requester_id=alice.id,
)
db.add(RequestHistory(request_id=r3.id, user_id=alice.id, action="created",
                       previous_status=None, new_status="draft"))

# 4. Approved request awaiting payment
r4 = make_request(
    title="Zoom annual subscription", amount=149.90, expense_date=today - timedelta(days=10),
    category=CategoryEnum.software_subscriptions, description="Annual renewal for program coordination calls.",
    status=StatusEnum.approved, requester_id=bob.id, reviewer_id=rachel.id,
    reviewer_comment="Approved, matches budgeted software costs.",
    submitted_at=today - timedelta(days=10), reviewed_at=today - timedelta(days=8),
)
db.add(RequestHistory(request_id=r4.id, user_id=bob.id, action="created",
                       previous_status=None, new_status="draft"))
db.add(RequestHistory(request_id=r4.id, user_id=bob.id, action="submitted",
                       previous_status="draft", new_status="submitted"))
db.add(RequestHistory(request_id=r4.id, user_id=rachel.id, action="approved",
                       previous_status="submitted", new_status="approved",
                       comment="Approved, matches budgeted software costs."))

# 5. Rejected request with a reason
r5 = make_request(
    title="Training course - unapproved vendor", amount=250.00, expense_date=today - timedelta(days=7),
    category=CategoryEnum.training, description="Online certification course.",
    status=StatusEnum.rejected, requester_id=alice.id, reviewer_id=rachel.id,
    rejection_reason="This training vendor is not on our approved list. Please resubmit with an approved provider.",
    submitted_at=today - timedelta(days=7), reviewed_at=today - timedelta(days=6),
)
db.add(RequestHistory(request_id=r5.id, user_id=alice.id, action="created",
                       previous_status=None, new_status="draft"))
db.add(RequestHistory(request_id=r5.id, user_id=alice.id, action="submitted",
                       previous_status="draft", new_status="submitted"))
db.add(RequestHistory(
    request_id=r5.id, user_id=rachel.id, action="rejected",
    previous_status="submitted", new_status="rejected",
    comment="This training vendor is not on our approved list. Please resubmit with an approved provider.",
))

# 6. Paid request
r6 = make_request(
    title="Event supplies - fundraiser gala", amount=530.75, expense_date=today - timedelta(days=20),
    category=CategoryEnum.event_expenses, description="Table linens, signage, and decorations.",
    status=StatusEnum.paid, requester_id=bob.id, reviewer_id=rachel.id,
    reviewer_comment="Approved ahead of the gala.",
    submitted_at=today - timedelta(days=20), reviewed_at=today - timedelta(days=18),
    paid_at=today - timedelta(days=14),
)
db.add(RequestHistory(request_id=r6.id, user_id=bob.id, action="created",
                       previous_status=None, new_status="draft"))
db.add(RequestHistory(request_id=r6.id, user_id=bob.id, action="submitted",
                       previous_status="draft", new_status="submitted"))
db.add(RequestHistory(request_id=r6.id, user_id=rachel.id, action="approved",
                       previous_status="submitted", new_status="approved"))
db.add(RequestHistory(request_id=r6.id, user_id=rachel.id, action="marked_paid",
                       previous_status="approved", new_status="paid"))

db.commit()
db.close()

print("Seed complete. Demo accounts (all passwords: password123):")
print("  requester : alice@example.com")
print("  requester : bob@example.com")
print("  reviewer  : rachel@example.com")
print("  admin     : admin@example.com")
