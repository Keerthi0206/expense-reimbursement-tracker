"""
Seeds the database with demo accounts and fictional sample reimbursement
requests covering every workflow state, for demo/testing purposes.

Run with: python seed.py
Options:
  --reset       Wipe existing users/requests first, then reseed from scratch
  --scale N     Also generate N additional synthetic requests (random
                category/amount/date/status) spread across the demo
                requesters, for load-testing or a fuller-looking demo
"""
import argparse
import random
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.core.db_setup import run_migrations
from app.core.security import hash_password
from app.models.models import (
    CategoryEnum,
    Notification,
    ReimbursementRequest,
    RequestHistory,
    RoleEnum,
    StatusEnum,
    User,
    UserAccountHistory,
)

parser = argparse.ArgumentParser(description="Seed the expense tracker database")
parser.add_argument("--reset", action="store_true", help="Wipe existing data first")
parser.add_argument("--scale", type=int, default=0, help="Add N extra synthetic requests")
args = parser.parse_args()

def add_synthetic_requests(db, alice, bob, rachel, count):
    titles = ["Client dinner", "Conference travel", "Software license", "Office chairs",
              "Team offsite", "Parking reimbursement", "Hotel stay", "Printer ink",
              "Catering", "Rideshare to airport"]
    categories = list(CategoryEnum)
    statuses_pool = [StatusEnum.submitted, StatusEnum.approved, StatusEnum.rejected, StatusEnum.paid]
    today = date.today()
    for i in range(count):
        requester = random.choice([alice, bob])
        status = random.choice(statuses_pool)
        expense_date = today - timedelta(days=random.randint(1, 180))
        req = ReimbursementRequest(
            title=f"{random.choice(titles)} #{i}",
            amount=round(random.uniform(10, 900), 2),
            expense_date=expense_date,
            category=random.choice(categories),
            status=status,
            requester_id=requester.id,
            reviewer_id=rachel.id if status != StatusEnum.submitted else None,
            submitted_at=expense_date,
            reviewed_at=expense_date + timedelta(days=1) if status != StatusEnum.submitted else None,
            paid_at=expense_date + timedelta(days=5) if status == StatusEnum.paid else None,
        )
        db.add(req)
    db.commit()
    print(f"Added {count} synthetic requests (--scale).")


run_migrations()
db = SessionLocal()

if args.reset:
    # child tables first -- both reference users and/or reimbursement_requests
    db.query(RequestHistory).delete()
    db.query(Notification).delete()
    db.query(UserAccountHistory).delete()
    db.query(ReimbursementRequest).delete()
    db.query(User).delete()
    db.commit()
    print("Existing data wiped (--reset).")

if db.query(User).count() > 0:
    if args.scale > 0:
        # already-seeded db + --scale alone: just add more requests to the
        # existing demo accounts, don't touch anything else
        alice = db.query(User).filter(User.email == "alice@example.com").first()
        bob = db.query(User).filter(User.email == "bob@example.com").first()
        rachel = db.query(User).filter(User.email == "rachel@example.com").first()
        if not (alice and bob and rachel):
            print("Database has data but not the expected demo accounts -- use --reset first.")
            db.close()
            raise SystemExit(1)
        add_synthetic_requests(db, alice, bob, rachel, args.scale)
        db.close()
        raise SystemExit(0)
    print("Database already has data. Skipping seed. Use --reset to wipe and reseed, "
          "or add --scale N on its own to just add more synthetic requests.")
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

if args.scale > 0:
    add_synthetic_requests(db, alice, bob, rachel, args.scale)

db.close()

print("Seed complete. Demo accounts (all passwords: password123):")
print("  requester : alice@example.com")
print("  requester : bob@example.com")
print("  reviewer  : rachel@example.com")
print("  admin     : admin@example.com")
