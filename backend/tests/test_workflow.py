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
