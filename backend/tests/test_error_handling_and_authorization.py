"""
Automated tests covering three specific hackathon requirements:
  - Invalid workflow actions should be prevented
  - Unauthorized actions should return appropriate errors
  - The application should handle invalid/unexpected input gracefully
    (no stack traces, DB errors, secrets, or raw exceptions reaching the client)

These were originally verified manually via curl against a live server
(see docs/testing.md) and are captured here as permanent regression tests.

Run with: pytest -v
"""
import os
import sys
import io

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
    db = SessionLocal()
    db.add_all([
        User(name="Guard Requester", email="guard_req@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.requester),
        User(name="Guard Requester Two", email="guard_req2@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.requester),
        User(name="Guard Reviewer", email="guard_rev@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.reviewer),
        User(name="Guard Admin", email="guard_admin@test.com",
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


def _make_submitted_request(req_token):
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Guard test request", "amount": 40.00, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    return request_id


# ---------- Invalid workflow actions are prevented ----------

class TestInvalidWorkflowActions:
    def test_cannot_approve_a_draft(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "Draft", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        assert resp.status_code == 400

    def test_cannot_reject_a_draft(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "Draft", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        resp = client.post(f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token), json={"reason": "no"})
        assert resp.status_code == 400

    def test_cannot_mark_paid_a_draft(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "Draft", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        assert resp.status_code == 400

    def test_cannot_submit_without_receipt(self):
        req_token = login("guard_req@test.com")
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "No receipt", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
        assert resp.status_code == 400

    def test_cannot_submit_an_already_submitted_request(self):
        req_token = login("guard_req@test.com")
        request_id = _make_submitted_request(req_token)
        resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
        assert resp.status_code == 400

    def test_cannot_mark_paid_a_merely_submitted_request(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(req_token)
        resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        assert resp.status_code == 400

    def test_cannot_approve_twice(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(req_token)
        client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        assert resp.status_code == 400

    def test_cannot_submit_a_paid_request(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(req_token)
        client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        resp = client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
        assert resp.status_code == 400

    def test_cannot_mark_paid_twice(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(req_token)
        client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        resp = client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        assert resp.status_code == 400

    def test_cannot_reject_a_paid_request(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(req_token)
        client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(rev_token), json={})
        client.post(f"/api/requests/{request_id}/mark-paid", headers=auth_headers(rev_token))
        resp = client.post(f"/api/requests/{request_id}/reject", headers=auth_headers(rev_token), json={"reason": "too late"})
        assert resp.status_code == 400


# ---------- Unauthorized actions return appropriate errors ----------

class TestUnauthorizedActions:
    def test_no_token_returns_401(self):
        resp = client.get("/api/requests")
        assert resp.status_code == 401

    def test_garbage_token_returns_401(self):
        resp = client.get("/api/requests", headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401

    def test_requester_cannot_approve_own_request(self):
        req_token = login("guard_req@test.com")
        request_id = _make_submitted_request(req_token)
        resp = client.post(f"/api/requests/{request_id}/approve", headers=auth_headers(req_token), json={})
        assert resp.status_code == 403

    def test_requester_cannot_view_someone_elses_request(self):
        req_token = login("guard_req@test.com")
        other_token = login("guard_req2@test.com")
        request_id = _make_submitted_request(req_token)
        resp = client.get(f"/api/requests/{request_id}", headers=auth_headers(other_token))
        assert resp.status_code == 403

    def test_requester_cannot_edit_someone_elses_request(self):
        req_token = login("guard_req@test.com")
        other_token = login("guard_req2@test.com")
        create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "Mine", "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        request_id = create_resp.json()["id"]
        resp = client.patch(f"/api/requests/{request_id}", headers=auth_headers(other_token), json={"title": "hacked"})
        assert resp.status_code == 403

    def test_reviewer_cannot_create_a_request(self):
        rev_token = login("guard_rev@test.com")
        resp = client.post("/api/requests", headers=auth_headers(rev_token), json={
            "title": "x", "amount": 1, "expense_date": "2026-01-05", "category": "other",
        })
        assert resp.status_code == 403

    def test_non_admin_blocked_from_admin_endpoint(self):
        req_token = login("guard_req@test.com")
        rev_token = login("guard_rev@test.com")
        assert client.get("/api/admin/users", headers=auth_headers(req_token)).status_code == 403
        assert client.get("/api/admin/users", headers=auth_headers(rev_token)).status_code == 403

    def test_requester_cannot_download_someone_elses_receipt(self):
        req_token = login("guard_req@test.com")
        other_token = login("guard_req2@test.com")
        request_id = _make_submitted_request(req_token)
        resp = client.get(f"/api/requests/{request_id}/receipt", headers=auth_headers(other_token))
        assert resp.status_code == 403

    def test_admin_cannot_approve_reject_or_pay_their_own_request(self):
        # admin passes the role gate, so the separate ownership check has to catch this
        admin_token = login("guard_admin@test.com")
        other_rev_token = login("guard_rev@test.com")
        request_id = _make_submitted_request(admin_token)

        approve_resp = client.post(
            f"/api/requests/{request_id}/approve", headers=auth_headers(admin_token), json={}
        )
        assert approve_resp.status_code == 403

        reject_resp = client.post(
            f"/api/requests/{request_id}/reject", headers=auth_headers(admin_token),
            json={"reason": "self reject"},
        )
        assert reject_resp.status_code == 403

        info_resp = client.post(
            f"/api/requests/{request_id}/request-info", headers=auth_headers(admin_token),
            json={"message": "need more info"},
        )
        assert info_resp.status_code == 403

        real_approve = client.post(
            f"/api/requests/{request_id}/approve", headers=auth_headers(other_rev_token), json={}
        )
        assert real_approve.status_code == 200

        paid_resp = client.post(
            f"/api/requests/{request_id}/mark-paid", headers=auth_headers(admin_token)
        )
        assert paid_resp.status_code == 403


# ---------- Graceful handling of invalid/unexpected input ----------

class TestGracefulErrorHandling:
    def test_malformed_json_body_does_not_crash(self):
        req_token = login("guard_req@test.com")
        resp = client.post(
            "/api/requests", headers={**auth_headers(req_token), "Content-Type": "application/json"},
            content=b'{"title": "x", "amount": }}}broken',
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "Traceback" not in str(body)
        assert "sqlite" not in str(body).lower()

    def test_sql_injection_style_id_is_treated_as_literal_data(self):
        req_token = login("guard_req@test.com")
        malicious_id = "'; DROP TABLE users; --"
        resp = client.get(f"/api/requests/{malicious_id}", headers=auth_headers(req_token))
        assert resp.status_code == 404
        assert "sql" not in resp.text.lower()
        assert "traceback" not in resp.text.lower()

        # table should still be intact
        assert client.post(
            "/api/auth/login", json={"email": "guard_req@test.com", "password": "pass1234"}
        ).status_code == 200

    def test_sql_injection_style_string_in_title_is_stored_as_plain_text(self):
        req_token = login("guard_req@test.com")
        payload_title = "'; DROP TABLE reimbursement_requests; --"
        resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": payload_title, "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        assert resp.status_code == 201
        assert resp.json()["title"] == payload_title

        assert client.get("/api/requests", headers=auth_headers(req_token)).status_code == 200

    def test_wrong_content_type_does_not_crash(self):
        req_token = login("guard_req@test.com")
        resp = client.post(
            "/api/requests", headers={**auth_headers(req_token), "Content-Type": "text/plain"},
            content=b"just plain text, not json",
        )
        assert resp.status_code == 422

    def test_empty_body_does_not_crash(self):
        req_token = login("guard_req@test.com")
        resp = client.post(
            "/api/requests", headers={**auth_headers(req_token), "Content-Type": "application/json"},
            content=b"",
        )
        assert resp.status_code == 422

    def test_oversized_field_is_rejected_not_crashed(self):
        req_token = login("guard_req@test.com")
        resp = client.post("/api/requests", headers=auth_headers(req_token), json={
            "title": "A" * 100_000, "amount": 10, "expense_date": "2026-01-05", "category": "other",
        })
        assert resp.status_code == 422

    def test_unhandled_error_response_never_contains_secret_values(self):
        req_token = login("guard_req@test.com")
        resp = client.get("/api/requests/does-not-exist-at-all", headers=auth_headers(req_token))
        assert resp.status_code == 404
        text_lower = resp.text.lower()
        for leak in ("secret", "password", "traceback", "site-packages", "/home/", "sqlalchemy.exc"):
            assert leak not in text_lower
