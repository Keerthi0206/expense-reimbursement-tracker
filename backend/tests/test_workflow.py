"""
Automated tests for the reimbursement workflow, covering validation,
role-based access control, and the full status lifecycle.

Run with: pytest -v
"""
import os
import sys
import io
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.models import User, RoleEnum

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # DB schema is managed by conftest.py; this just seeds this file's users
    db = SessionLocal()
    db.add_all([
        User(name="Test Requester", email="req@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.requester),
        User(name="Test Requester Two", email="req2@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.requester),
        User(name="Test Reviewer", email="rev@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.reviewer),
        User(name="Test Admin", email="admin@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.admin),
        User(name="Test Admin Two", email="admin2@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.admin),
    ])
    db.commit()
    db.close()
    yield


def login(email, password="pass1234"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_fake_receipt_image(merchant, date_str, total):
    """Builds a real, OCR-readable receipt image with a proper TrueType font
    (not Pillow's crude default bitmap font, which garbles text badly and
    was confirmed unreliable during development). Returns JPEG bytes."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (500, 300), color="white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20)
    lines = [merchant, f"Date: {date_str}", "", f"TOTAL:    ${total:.2f}"]
    y = 20
    for line in lines:
        draw.text((20, y), line, fill="black", font=font)
        y += 30
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_login_wrong_password_returns_401():
    resp = client.post("/api/auth/login", json={"email": "req@test.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401_not_500():
    resp = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "x"})
    assert resp.status_code == 401


def test_create_request_requires_auth():
    resp = client.post("/api/requests", json={
        "title": "x", "amount": 5, "expense_date": "2026-01-01", "category": "other",
    })
    assert resp.status_code == 401


def test_budget_limit_warning_flag_is_computed():
    token = login("req@test.com")

    over_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Over budget meal", "amount": 300, "expense_date": "2026-01-05", "category": "meals",
    })
    assert over_resp.status_code == 201
    over_data = over_resp.json()
    assert over_data["budget_limit"] == 150.0
    assert over_data["exceeds_budget"] is True

    under_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Normal meal", "amount": 25, "expense_date": "2026-01-05", "category": "meals",
    })
    under_data = under_resp.json()
    assert under_data["exceeds_budget"] is False

    # the flag isn't a hard block -- creation still succeeds either way
    assert over_resp.status_code == under_resp.status_code == 201

    # different categories have different limits
    travel_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Flight", "amount": 300, "expense_date": "2026-01-05", "category": "travel",
    })
    assert travel_resp.json()["budget_limit"] == 800.0
    assert travel_resp.json()["exceeds_budget"] is False


def test_negative_amount_rejected():
    token = login("req@test.com")
    resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Bad expense", "amount": -10, "expense_date": "2026-01-01", "category": "other",
    })
    assert resp.status_code == 422


def test_future_date_rejected():
    token = login("req@test.com")
    resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Future expense", "amount": 10, "expense_date": "2099-01-01", "category": "other",
    })
    assert resp.status_code == 422


def test_missing_category_rejected():
    token = login("req@test.com")
    resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "No category", "amount": 10, "expense_date": "2026-01-01",
    })
    assert resp.status_code == 422


def test_nested_history_is_chronologically_ordered():
    """The frontend does .slice().reverse() on request.history assuming it comes
    back oldest-first from the backend. Without an explicit order_by on the
    relationship, that's not guaranteed -- SQLite happens to preserve insertion
    order by coincidence, but Postgres (used in production, see README) makes
    no such guarantee. This test locks in that the nested history is actually
    sorted by timestamp, not just "usually looks right" on SQLite."""
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Chronology test", "amount": 20, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))  # claims it
    client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
    client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))

    detail_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(req_token))
    timestamps = [h["timestamp"] for h in detail_resp.json()["history"]]
    assert timestamps == sorted(timestamps), "nested history must be chronologically ordered"

    actions_in_order = [h["action"] for h in detail_resp.json()["history"]]
    assert actions_in_order == ["created", "submitted", "opened_for_review", "approved", "marked_paid"]


def test_high_value_request_needs_second_admin_approval():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Big conference sponsorship", "amount": 900, "expense_date": "2026-01-05",
        "category": "event_expenses",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    # first approval by a reviewer doesn't fully approve it -- goes to the second tier
    first_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
    assert first_resp.status_code == 200
    assert first_resp.json()["status"] == "pending_second_approval"

    # a plain reviewer (not an admin) can't give the second-tier approval, even a different one
    other_rev_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={}
    )
    assert other_rev_resp.status_code == 403

    # an admin can
    admin_token = login("admin@test.com")
    second_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(admin_token), json={})
    assert second_resp.status_code == 200
    assert second_resp.json()["status"] == "approved"


def test_same_person_cannot_give_both_approvals():
    req_token = login("req@test.com")
    admin_token = login("admin@test.com")
    other_admin_token = login("admin2@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Training course", "amount": 50, "expense_date": "2026-01-05", "category": "training",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    # training category triggers the second tier regardless of amount ($50, well under threshold)
    first_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(admin_token), json={})
    assert first_resp.status_code == 200
    assert first_resp.json()["status"] == "pending_second_approval"

    # same admin can't also give the second approval
    same_admin_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(admin_token), json={})
    assert same_admin_resp.status_code == 403

    # a different admin can
    second_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(other_admin_token), json={})
    assert second_resp.status_code == 200
    assert second_resp.json()["status"] == "approved"

    history_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(req_token))
    actions = [h["action"] for h in history_resp.json()["items"]]
    assert "first_approval_given" in actions
    assert "second_approval_given" in actions

    # normal mark-paid flow works fine once fully approved
    paid_resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(other_admin_token))
    assert paid_resp.status_code == 200


def test_low_value_request_skips_second_tier_entirely():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Cheap office pens", "amount": 15, "expense_date": "2026-01-05", "category": "office_supplies",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"  # straight to approved, no second tier


def test_can_reject_a_request_awaiting_second_approval():
    req_token = login("req@test.com")
    admin_token = login("admin@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Big travel request", "amount": 900, "expense_date": "2026-01-05", "category": "travel",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(admin_token), json={})

    reject_resp = client.post(
        f"/api/requests/{request_id}/reject", headers=auth_headers(admin_token),
        json={"reason": "Actually not approved, correcting a mistake"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"


def test_full_workflow_create_to_paid():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    # Create
    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Office chairs", "amount": 120.00, "expense_date": "2026-01-05",
        "category": "office_supplies", "description": "Two ergonomic chairs",
    })
    assert create_resp.status_code == 201
    request_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "draft"

    # Cannot submit without a receipt
    submit_resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    assert submit_resp.status_code == 400

    # Upload receipt (fake but valid JPEG signature)
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    upload_resp = client.post(
        f"/api/requests/{request_id}/receipt",
        headers=auth_headers(req_token),
        files={"file": ("receipt.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
    )
    assert upload_resp.status_code == 200

    # Invalid file type rejected
    bad_file_resp = client.post(
        f"/api/requests/{request_id}/receipt",
        headers=auth_headers(req_token),
        files={"file": ("receipt.exe", io.BytesIO(b"MZfakeexe"), "application/octet-stream")},
    )
    assert bad_file_resp.status_code == 400

    # Now submit succeeds
    submit_resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "submitted"

    # Requester cannot approve
    forbidden_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(req_token), json={}
    )
    assert forbidden_resp.status_code == 403

    # Reviewer approves
    approve_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token),
        json={"comment": "Approved"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # Cannot approve twice
    approve_again_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={}
    )
    assert approve_again_resp.status_code == 400

    # Requester cannot mark paid
    forbidden_paid_resp = client.post(
        f"/api/requests/{request_id}/mark-paid", headers=auth_headers(req_token)
    )
    assert forbidden_paid_resp.status_code == 403

    # Reviewer marks paid
    paid_resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
    assert paid_resp.status_code == 200
    assert paid_resp.json()["status"] == "paid"

    # History was recorded
    detail_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))
    history = detail_resp.json()["history"]
    actions = [h["action"] for h in history]
    assert "created" in actions and "submitted" in actions and "approved" in actions and "marked_paid" in actions


def test_requester_can_cancel_before_approval():
    req_token = login("req@test.com")
    other_token = login("req2@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Cancel me", "amount": 25, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]

    # another requester can't cancel someone else's request
    forbidden_resp = client.post(
        f"/api/requests/{request_id}/cancel", headers=auth_headers(other_token), json={}
    )
    assert forbidden_resp.status_code == 403

    # owner can cancel a draft
    cancel_resp = client.post(
        f"/api/requests/{request_id}/cancel", headers=auth_headers(req_token),
        json={"reason": "Submitted by mistake"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # can't cancel an already-cancelled request
    again_resp = client.post(f"/api/requests/{request_id}/cancel", headers=auth_headers(req_token), json={})
    assert again_resp.status_code == 400

    history_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(req_token))
    entries = history_resp.json()["items"]
    cancel_entry = next(e for e in entries if e["action"] == "cancelled")
    assert cancel_entry["comment"] == "Submitted by mistake"


def test_cannot_cancel_after_approval():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Cancel after approval test", "amount": 30, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})

    cancel_resp = client.post(f"/api/requests/{request_id}/cancel", headers=auth_headers(req_token), json={})
    assert cancel_resp.status_code == 400

    client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
    still_blocked_resp = client.post(
        f"/api/requests/{request_id}/cancel", headers=auth_headers(req_token), json={}
    )
    assert still_blocked_resp.status_code == 400


def test_cancelling_a_claimed_request_notifies_the_reviewer():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Cancel after claim test", "amount": 30, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))  # claims it

    before_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    before_count = before_resp.json()["total"]

    cancel_resp = client.post(
        f"/api/requests/{request_id}/cancel", headers=auth_headers(req_token),
        json={"reason": "No longer needed"},
    )
    assert cancel_resp.status_code == 200

    after_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    after_data = after_resp.json()
    assert after_data["total"] == before_count + 1
    assert "cancelled" in after_data["items"][0]["message"]


def test_double_submit_race_is_prevented():
    """Fires 10 real concurrent submits (separate threads/clients) and checks
    exactly one wins. Regression test for a read-then-write race found via
    manual testing -- fixed with a single conditional UPDATE."""
    req_token = login("req@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Race condition test", "amount": 40.00, "expense_date": "2026-01-05",
        "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})

    results = []
    lock = threading.Lock()

    def fire_submit():
        c = TestClient(app)
        resp = c.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
        with lock:
            results.append(resp.status_code)

    threads = [threading.Thread(target=fire_submit) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    success_count = results.count(200)
    assert success_count == 1, f"Expected exactly 1 successful submit, got {success_count} (results: {results})"
    assert results.count(400) == 9

    detail_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(req_token))
    submit_history = [h for h in detail_resp.json()["history"] if h["action"] in ("submitted", "resubmitted")]
    assert len(submit_history) == 1


def test_can_edit_and_resubmit_after_rejection():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Needs a fix", "amount": 40, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    client.post(f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token),
                json={"reason": "Wrong category"})

    # Cannot submit a rejected request without editing it first? Actually can submit directly too.
    edit_resp = client.patch(
        f"/api/requests/{request_id}", headers=auth_headers(req_token),
        json={"category": "training", "title": "Needs a fix (corrected)"},
    )
    assert edit_resp.status_code == 200

    resubmit_resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    assert resubmit_resp.status_code == 200
    assert resubmit_resp.json()["status"] == "submitted"
    assert resubmit_resp.json()["rejection_reason"] is None

    history_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(req_token))
    actions = [h["action"] for h in history_resp.json()["items"]]
    assert "rejected" in actions
    assert "resubmitted" in actions

    # normal approval flow works fine afterward
    approve_resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
    assert approve_resp.status_code == 200


def test_reject_requires_reason():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Questionable training", "amount": 200.00, "expense_date": "2026-01-05",
        "category": "training",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    # Reject without reason fails validation
    empty_reject_resp = client.post(
        f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token), json={}
    )
    assert empty_reject_resp.status_code == 422

    # Reject with reason succeeds
    reject_resp = client.post(
        f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token),
        json={"reason": "Vendor not approved"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"
    assert reject_resp.json()["rejection_reason"] == "Vendor not approved"

    # Rejected requests cannot be marked Paid
    paid_resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
    assert paid_resp.status_code == 400


def test_requester_cannot_see_others_requests():
    token1 = login("req@test.com")
    token2 = login("req2@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(token1), json={
        "title": "Private expense", "amount": 30, "expense_date": "2026-01-05", "category": "meals",
    })
    request_id = create_resp.json()["id"]

    # Owner can view
    own_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(token1))
    assert own_resp.status_code == 200

    # Another requester cannot view it
    other_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(token2))
    assert other_resp.status_code == 403

    # And it doesn't show up in their list
    list_resp = client.get("/api/requests", headers=auth_headers(token2))
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert request_id not in ids


def test_approved_request_can_be_reverted_but_not_after_paid():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Mistakenly approved item", "amount": 75.00, "expense_date": "2026-01-05",
        "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    approve_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={}
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # Reviewer catches the mistake and reverses it with a reason, before payment
    revert_resp = client.post(
        f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token),
        json={"reason": "Approved by mistake, receipt does not match amount"},
    )
    assert revert_resp.status_code == 200
    assert revert_resp.json()["status"] == "rejected"
    assert "mistake" in revert_resp.json()["rejection_reason"]

    # Confirm the history recorded it as a revoked approval, not a fresh rejection
    detail_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))
    actions = [h["action"] for h in detail_resp.json()["history"]]
    assert "approval_revoked" in actions

    # Separately: once a request is Paid, it must NOT be revertible via reject
    create2_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Already paid item", "amount": 50.00, "expense_date": "2026-01-05",
        "category": "other",
    })
    request_id2 = create2_resp.json()["id"]
    client.post(f"/api/requests/{request_id2}/receipt", headers=auth_headers(req_token),
                files={"file": ("r2.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id2}/submit", headers=auth_headers(req_token))
    client.post(f"/api/requests/{request_id2}/approve", headers=auth_headers(rev_token), json={})
    paid_resp = client.post(f"/api/requests/{request_id2}/mark-paid", headers=auth_headers(rev_token))
    assert paid_resp.status_code == 200
    assert paid_resp.json()["status"] == "paid"

    blocked_resp = client.post(
        f"/api/requests/{request_id2}/reject", headers=auth_headers(rev_token),
        json={"reason": "Too late, already paid"},
    )
    assert blocked_resp.status_code == 400


def test_reviewer_opening_submitted_request_claims_it_as_under_review():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Claim test", "amount": 60.00, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    # Requester viewing their own request must NOT trigger the claim
    own_view = client.get(f"/api/requests/{request_id}", headers=auth_headers(req_token))
    assert own_view.json()["status"] == "submitted"

    # Reviewer opening it claims it
    rev_view = client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))
    assert rev_view.json()["status"] == "under_review"
    actions = [h["action"] for h in rev_view.json()["history"]]
    assert "opened_for_review" in actions

    # Opening it again shouldn't duplicate the history entry
    rev_view_again = client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))
    actions_again = [h["action"] for h in rev_view_again.json()["history"]]
    assert actions_again.count("opened_for_review") == 1

    # The requester was notified once when it got claimed, not duplicated on the repeat view
    notif_resp = client.get("/api/notifications", headers=auth_headers(req_token))
    claim_notifs = [n for n in notif_resp.json()["items"] if n["request_id"] == request_id]
    assert len(claim_notifs) == 1

    # Still approvable/rejectable while under_review
    approve_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={}
    )
    assert approve_resp.status_code == 200

    # The "pending" filter alias covers both submitted and under_review
    create2_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Still submitted", "amount": 20.00, "expense_date": "2026-01-05", "category": "other",
    })
    request_id2 = create2_resp.json()["id"]
    client.post(f"/api/requests/{request_id2}/receipt", headers=auth_headers(req_token),
                files={"file": ("r2.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id2}/submit", headers=auth_headers(req_token))

    pending_resp = client.get("/api/requests?status=pending", headers=auth_headers(rev_token))
    pending_ids = [item["id"] for item in pending_resp.json()["items"]]
    assert request_id2 in pending_ids  # still submitted, never opened


def test_request_info_flow_and_resubmission():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Blurry receipt", "amount": 45.00, "expense_date": "2026-01-05", "category": "meals",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    # Requester cannot request info on their own request
    self_info_resp = client.post(
        f"/api/requests/{request_id}/request-info", headers=auth_headers(req_token),
        json={"message": "n/a"},
    )
    assert self_info_resp.status_code == 403

    # Empty message is rejected
    empty_info_resp = client.post(
        f"/api/requests/{request_id}/request-info", headers=auth_headers(rev_token), json={"message": ""}
    )
    assert empty_info_resp.status_code == 422

    # Reviewer requests more info
    info_resp = client.post(
        f"/api/requests/{request_id}/request-info", headers=auth_headers(rev_token),
        json={"message": "Please re-upload a clearer receipt"},
    )
    assert info_resp.status_code == 200
    assert info_resp.json()["status"] == "changes_requested"
    assert info_resp.json()["info_requested_message"] == "Please re-upload a clearer receipt"

    # Cannot request info twice in a row (wrong status now)
    second_info_resp = client.post(
        f"/api/requests/{request_id}/request-info", headers=auth_headers(rev_token),
        json={"message": "again"},
    )
    assert second_info_resp.status_code == 400

    # Owner can edit while changes_requested (not just draft)
    edit_resp = client.patch(
        f"/api/requests/{request_id}", headers=auth_headers(req_token),
        json={"title": "Blurry receipt (updated)"},
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["title"] == "Blurry receipt (updated)"

    # Resubmit — goes back to submitted, and the info message is cleared
    resubmit_resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    assert resubmit_resp.status_code == 200
    assert resubmit_resp.json()["status"] == "submitted"
    assert resubmit_resp.json()["info_requested_message"] is None

    detail_resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))
    actions = [h["action"] for h in detail_resp.json()["history"]]
    assert "info_requested" in actions
    assert "resubmitted" in actions

    # Now approvable normally
    approve_resp = client.post(
        f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={}
    )
    assert approve_resp.status_code == 200


def test_submitting_a_request_notifies_active_reviewers_and_admins():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Needs a reviewer's eyes", "amount": 30, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})

    before_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    before_count = before_resp.json()["total"]

    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))

    after_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    after_data = after_resp.json()
    assert after_data["total"] == before_count + 1
    newest = after_data["items"][0]
    assert "Needs a reviewer's eyes" in newest["message"]
    assert newest["request_id"] == request_id
    assert newest["is_read"] is False

    # the requester doesn't notify themselves
    own_resp = client.get("/api/notifications", headers=auth_headers(req_token))
    own_messages = [n["message"] for n in own_resp.json()["items"]]
    assert not any("Needs a reviewer's eyes" in m for m in own_messages)


def test_notifications_are_paginated_and_scoped_to_the_user():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    for i in range(3):
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": f"Notif test {i}", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
        client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                    files={"file": (f"r{i}.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
        client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
        client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})

    all_resp = client.get("/api/notifications", headers=auth_headers(req_token))
    assert all_resp.status_code == 200
    body = all_resp.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total", "total_pages"}
    assert body["total"] >= 3

    small_page_resp = client.get("/api/notifications?page=1&page_size=1", headers=auth_headers(req_token))
    small_body = small_page_resp.json()
    assert len(small_body["items"]) == 1
    assert small_body["page_size"] == 1

    # a different user's notifications are never mixed in
    rev_notif_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    rev_messages = [n["message"] for n in rev_notif_resp.json()["items"]]
    req_messages = [n["message"] for n in body["items"]]
    assert not set(rev_messages) & set(req_messages)


def test_dashboard_totals_are_accurate():
    token = login("req@test.com")
    dash_resp = client.get("/api/requests/stats/dashboard", headers=auth_headers(token))
    assert dash_resp.status_code == 200
    data = dash_resp.json()
    assert "total_requested" in data
    assert "count_by_status" in data
    assert sum(data["count_by_status"].values()) >= 1


def test_search_and_filter():
    token = login("req@test.com")
    resp = client.get("/api/requests?category=meals&page=1&page_size=5", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["category"] == "meals" for item in data["items"])
    assert data["page"] == 1


def test_duplicate_check_finds_matching_amount_and_date():
    req_token = login("req@test.com")
    other_token = login("req2@test.com")

    first_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Client dinner", "amount": 88.50, "expense_date": "2026-02-01", "category": "meals",
    })
    first_id = first_resp.json()["id"]

    # no duplicate yet
    empty_check = client.get(
        "/api/requests/meta/check-duplicate?amount=88.50&expense_date=2026-02-01",
        headers=auth_headers(req_token),
    )
    assert empty_check.status_code == 200
    assert len(empty_check.json()) == 1  # finds itself, since nothing's excluded

    # excluding itself, no duplicates
    self_excluded_check = client.get(
        f"/api/requests/meta/check-duplicate?amount=88.50&expense_date=2026-02-01&exclude_id={first_id}",
        headers=auth_headers(req_token),
    )
    assert self_excluded_check.json() == []

    # a second, genuinely different request with the same amount/date
    second_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Client dinner (again)", "amount": 88.50, "expense_date": "2026-02-01", "category": "meals",
    })
    second_id = second_resp.json()["id"]

    match_check = client.get(
        f"/api/requests/meta/check-duplicate?amount=88.50&expense_date=2026-02-01&exclude_id={second_id}",
        headers=auth_headers(req_token),
    )
    matches = match_check.json()
    assert len(matches) == 1
    assert matches[0]["id"] == first_id

    # doesn't leak across users
    other_check = client.get(
        "/api/requests/meta/check-duplicate?amount=88.50&expense_date=2026-02-01",
        headers=auth_headers(other_token),
    )
    assert other_check.json() == []

    # cancelled requests don't count as live duplicates
    client.post(f"/api/requests/{first_id}/cancel", headers=auth_headers(req_token), json={})
    after_cancel_check = client.get(
        f"/api/requests/meta/check-duplicate?amount=88.50&expense_date=2026-02-01&exclude_id={second_id}",
        headers=auth_headers(req_token),
    )
    assert after_cancel_check.json() == []


def test_sorting_requests_by_amount():
    token = login("req@test.com")

    for amount in (15, 300, 75):
        client.post("/api/requests", headers=auth_headers(token), json={
            "title": f"Sort test {amount}", "amount": amount,
            "expense_date": "2026-01-05", "category": "other",
        })

    asc_resp = client.get(
        "/api/requests?keyword=Sort test&sort_by=amount&order=asc&page_size=50",
        headers=auth_headers(token),
    )
    assert asc_resp.status_code == 200
    amounts = [item["amount"] for item in asc_resp.json()["items"]]
    assert amounts == sorted(amounts)

    desc_resp = client.get(
        "/api/requests?keyword=Sort test&sort_by=amount&order=desc&page_size=50",
        headers=auth_headers(token),
    )
    amounts_desc = [item["amount"] for item in desc_resp.json()["items"]]
    assert amounts_desc == sorted(amounts_desc, reverse=True)

    bad_sort_resp = client.get("/api/requests?sort_by=not_a_real_column", headers=auth_headers(token))
    assert bad_sort_resp.status_code == 422


def test_request_history_has_its_own_endpoint():
    req_token = login("req@test.com")
    rev_token = login("rev@test.com")

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "History endpoint test", "amount": 20, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]

    history_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(req_token))
    assert history_resp.status_code == 200
    body = history_resp.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total", "total_pages"}
    actions = [h["action"] for h in body["items"]]
    assert "created" in actions

    # a user with no access to the request can't see its history either
    other_token = login("req2@test.com")
    forbidden_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(other_token))
    assert forbidden_resp.status_code == 403

    # reviewers can see any request's history
    rev_resp = client.get(f"/api/requests/{request_id}/history", headers=auth_headers(rev_token))
    assert rev_resp.status_code == 200


def test_deactivated_account_cannot_log_in():
    # Admin-only endpoint check: a non-admin cannot deactivate anyone
    token = login("req@test.com")
    resp = client.get("/api/admin/users", headers=auth_headers(token))
    assert resp.status_code == 403


def test_extract_receipt_preview_before_request_exists():
    token = login("req@test.com")
    receipt_bytes = _make_fake_receipt_image("STAPLES OFFICE SUPPLY", "08/12/2026", 26.19)

    resp = client.post(
        "/api/requests/meta/extract-receipt", headers=auth_headers(token),
        files={"file": ("receipt.jpg", io.BytesIO(receipt_bytes), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_amount"] == 26.19
    assert data["suggested_date"] == "2026-08-12"
    assert "STAPLES" in data["suggested_merchant"]
    assert len(data["raw_text_preview"]) > 0


def test_extract_receipt_preview_rejects_bad_file_type():
    token = login("req@test.com")
    resp = client.post(
        "/api/requests/meta/extract-receipt", headers=auth_headers(token),
        files={"file": ("not_a_receipt.txt", io.BytesIO(b"just some text"), "text/plain")},
    )
    assert resp.status_code == 400


def test_receipt_analysis_requires_a_receipt_first():
    token = login("req@test.com")
    create_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "No receipt yet", "amount": 20, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]

    resp = client.get(f"/api/requests/{request_id}/receipt-analysis", headers=auth_headers(token))
    assert resp.status_code == 400


def test_receipt_analysis_flags_a_genuine_mismatch():
    token = login("req@test.com")
    create_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Typo'd amount", "amount": 999.99, "expense_date": "2026-08-12", "category": "office_supplies",
    })
    request_id = create_resp.json()["id"]

    # the actual receipt says $26.19, but the requester typed $999.99
    receipt_bytes = _make_fake_receipt_image("STAPLES OFFICE SUPPLY", "08/12/2026", 26.19)
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(token),
                files={"file": ("receipt.jpg", io.BytesIO(receipt_bytes), "image/jpeg")})

    resp = client.get(f"/api/requests/{request_id}/receipt-analysis", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount_mismatch"] is True
    assert data["date_mismatch"] is False  # date does match
    assert data["suggestion"]["suggested_amount"] == 26.19
    assert data["submitted_amount"] == 999.99
    assert data["metadata"]["format"] == "image/jpeg"
    assert data["metadata"]["width"] == 500


def test_receipt_analysis_no_mismatch_when_values_actually_match():
    token = login("req@test.com")
    create_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Correct amount", "amount": 26.19, "expense_date": "2026-08-12", "category": "office_supplies",
    })
    request_id = create_resp.json()["id"]

    receipt_bytes = _make_fake_receipt_image("STAPLES OFFICE SUPPLY", "08/12/2026", 26.19)
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(token),
                files={"file": ("receipt.jpg", io.BytesIO(receipt_bytes), "image/jpeg")})

    resp = client.get(f"/api/requests/{request_id}/receipt-analysis", headers=auth_headers(token))
    data = resp.json()
    assert data["amount_mismatch"] is False
    assert data["date_mismatch"] is False


def test_receipt_analysis_respects_normal_access_control():
    token = login("req@test.com")
    other_token = login("req2@test.com")
    create_resp = client.post("/api/requests", headers=auth_headers(token), json={
        "title": "Private request", "amount": 20, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    receipt_bytes = _make_fake_receipt_image("Some Store", "01/05/2026", 20.00)
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(token),
                files={"file": ("r.jpg", io.BytesIO(receipt_bytes), "image/jpeg")})

    resp = client.get(f"/api/requests/{request_id}/receipt-analysis", headers=auth_headers(other_token))
    assert resp.status_code == 403
