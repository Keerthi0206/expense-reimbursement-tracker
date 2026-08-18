"""
Automated tests for admin user management: listing, role/status changes,
self-protection guards, and the account-history audit trail.

Run with: pytest -v
"""
import os
import sys
import io
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.models import User, RoleEnum, ReimbursementRequest

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # DB schema is managed by conftest.py; this just seeds this file's users
    db = SessionLocal()
    db.add_all([
        User(name="Admin One", email="admin1@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.admin),
        User(name="Plain Requester", email="requester@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.requester),
        User(name="Plain Reviewer", email="reviewer@test.com",
             hashed_password=hash_password("pass1234"), role=RoleEnum.reviewer),
    ])
    db.commit()
    db.close()
    yield


def login(email, password="pass1234"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    data = resp.json()
    return data["access_token"], data["user"]["id"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_list_users():
    token, _ = login("requester@test.com")
    resp = client.get("/api/admin/users", headers=auth_headers(token))
    assert resp.status_code == 403


def test_admin_can_list_users_with_full_fields():
    admin_token, _ = login("admin1@test.com")
    resp = client.get("/api/admin/users", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    users = data["items"]
    assert data["total"] >= 3
    assert len(users) >= 3
    # Confirm every field the admin brief asks for is present
    sample = users[0]
    for field in ("id", "name", "email", "role", "is_active", "created_at"):
        assert field in sample


def test_admin_users_list_supports_pagination_filtering_and_sorting():
    admin_token, _ = login("admin1@test.com")

    page_resp = client.get("/api/admin/users?page=1&page_size=2", headers=auth_headers(admin_token))
    assert page_resp.status_code == 200
    page_data = page_resp.json()
    assert page_data["page"] == 1
    assert page_data["page_size"] == 2
    assert len(page_data["items"]) <= 2

    role_resp = client.get("/api/admin/users?role=admin", headers=auth_headers(admin_token))
    assert role_resp.status_code == 200
    assert all(u["role"] == "admin" for u in role_resp.json()["items"])

    active_resp = client.get("/api/admin/users?is_active=true", headers=auth_headers(admin_token))
    assert active_resp.status_code == 200
    assert all(u["is_active"] is True for u in active_resp.json()["items"])

    sorted_resp = client.get("/api/admin/users?sort_by=name&order=asc", headers=auth_headers(admin_token))
    assert sorted_resp.status_code == 200
    names = [u["name"] for u in sorted_resp.json()["items"]]
    assert names == sorted(names)

    bad_role_resp = client.get("/api/admin/users?role=not-a-role", headers=auth_headers(admin_token))
    assert bad_role_resp.status_code == 422


def test_admin_users_search_matches_name_or_email():
    admin_token, _ = login("admin1@test.com")

    by_name_resp = client.get("/api/admin/users?search=requester", headers=auth_headers(admin_token))
    assert by_name_resp.status_code == 200
    assert len(by_name_resp.json()["items"]) >= 1
    assert all("requester" in u["name"].lower() for u in by_name_resp.json()["items"])

    by_email_resp = client.get("/api/admin/users?search=@test.com", headers=auth_headers(admin_token))
    assert by_email_resp.status_code == 200
    assert len(by_email_resp.json()["items"]) >= 1

    no_match_resp = client.get("/api/admin/users?search=nobodyhasthisname", headers=auth_headers(admin_token))
    assert no_match_resp.json()["items"] == []


def test_reason_is_recorded_for_role_and_status_changes():
    admin_token, admin_id = login("admin1@test.com")
    _, reviewer_id = login("reviewer@test.com")

    role_resp = client.patch(
        f"/api/admin/users/{reviewer_id}/role", headers=auth_headers(admin_token),
        json={"role": "admin", "reason": "Promoted to help manage the pilot rollout"},
    )
    assert role_resp.status_code == 200

    deactivate_resp = client.patch(
        f"/api/admin/users/{reviewer_id}/status", headers=auth_headers(admin_token),
        json={"is_active": False, "reason": "Left the organization"},
    )
    assert deactivate_resp.status_code == 200

    history_resp = client.get(
        f"/api/admin/users/{reviewer_id}/history", headers=auth_headers(admin_token)
    )
    entries = history_resp.json()["items"]
    role_entry = next(e for e in entries if e["action"] == "role_changed" and e["new_value"] == "admin")
    assert role_entry["reason"] == "Promoted to help manage the pilot rollout"
    deactivate_entry = next(e for e in entries if e["action"] == "deactivated")
    assert deactivate_entry["reason"] == "Left the organization"

    # revert for other tests
    client.patch(f"/api/admin/users/{reviewer_id}/status", headers=auth_headers(admin_token),
                 json={"is_active": True})
    client.patch(f"/api/admin/users/{reviewer_id}/role", headers=auth_headers(admin_token),
                 json={"role": "reviewer"})


def test_admin_can_change_a_users_role_and_it_is_logged():
    admin_token, admin_id = login("admin1@test.com")
    _, requester_id = login("requester@test.com")

    resp = client.patch(
        f"/api/admin/users/{requester_id}/role", headers=auth_headers(admin_token),
        json={"role": "reviewer"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "reviewer"

    history_resp = client.get(
        f"/api/admin/users/{requester_id}/history", headers=auth_headers(admin_token)
    )
    assert history_resp.status_code == 200
    entries = history_resp.json()["items"]
    role_change = next(e for e in entries if e["action"] == "role_changed")
    assert role_change["previous_value"] == "requester"
    assert role_change["new_value"] == "reviewer"
    assert role_change["performed_by_id"] == admin_id

    # revert for other tests
    client.patch(f"/api/admin/users/{requester_id}/role", headers=auth_headers(admin_token),
                 json={"role": "requester"})


def test_admin_cannot_change_their_own_role():
    admin_token, admin_id = login("admin1@test.com")
    resp = client.patch(
        f"/api/admin/users/{admin_id}/role", headers=auth_headers(admin_token),
        json={"role": "requester"},
    )
    assert resp.status_code == 400


def test_admin_can_deactivate_and_reactivate_a_user_with_history():
    admin_token, admin_id = login("admin1@test.com")
    _, reviewer_id = login("reviewer@test.com")

    deactivate_resp = client.patch(
        f"/api/admin/users/{reviewer_id}/status", headers=auth_headers(admin_token),
        json={"is_active": False},
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    # Deactivated user can no longer log in
    blocked_login = client.post(
        "/api/auth/login", json={"email": "reviewer@test.com", "password": "pass1234"}
    )
    assert blocked_login.status_code == 403

    reactivate_resp = client.patch(
        f"/api/admin/users/{reviewer_id}/status", headers=auth_headers(admin_token),
        json={"is_active": True},
    )
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True

    history_resp = client.get(
        f"/api/admin/users/{reviewer_id}/history", headers=auth_headers(admin_token)
    )
    actions = [e["action"] for e in history_resp.json()["items"]]
    assert "deactivated" in actions
    assert "activated" in actions


def test_admin_cannot_deactivate_self():
    admin_token, admin_id = login("admin1@test.com")
    resp = client.patch(
        f"/api/admin/users/{admin_id}/status", headers=auth_headers(admin_token),
        json={"is_active": False},
    )
    assert resp.status_code == 400


def test_creating_a_user_is_logged_in_history():
    admin_token, _ = login("admin1@test.com")
    create_resp = client.post(
        "/api/admin/users", headers=auth_headers(admin_token),
        json={"name": "New Hire", "email": "newhire@test.com", "password": "pass1234", "role": "requester"},
    )
    assert create_resp.status_code == 201
    new_user_id = create_resp.json()["id"]

    history_resp = client.get(
        f"/api/admin/users/{new_user_id}/history", headers=auth_headers(admin_token)
    )
    actions = [e["action"] for e in history_resp.json()["items"]]
    assert "created" in actions


def test_non_admin_cannot_view_or_modify_user_history():
    token, _ = login("requester@test.com")
    admin_token, admin_id = login("admin1@test.com")
    resp = client.get(f"/api/admin/users/{admin_id}/history", headers=auth_headers(token))
    assert resp.status_code == 403


def test_reminders_go_out_for_stale_pending_requests():
    admin_token, _ = login("admin1@test.com")
    req_token, _ = login("requester@test.com")
    rev_token, rev_id = login("reviewer@test.com")

    # non-admin can't trigger reminders
    forbidden_resp = client.post("/api/admin/trigger-reminders", headers=auth_headers(req_token))
    assert forbidden_resp.status_code == 403

    create_resp = client.post("/api/requests", headers=auth_headers(req_token), json={
        "title": "Stale request", "amount": 40, "expense_date": "2026-01-05", "category": "other",
    })
    request_id = create_resp.json()["id"]
    fake_jpeg = b"\xff\xd8\xff" + b"0" * 20
    client.post(f"/api/requests/{request_id}/receipt", headers=auth_headers(req_token),
                files={"file": ("r.jpg", io.BytesIO(fake_jpeg), "image/jpeg")})
    client.post(f"/api/requests/{request_id}/submit", headers=auth_headers(req_token))
    # claim it, so the reminder targets this specific reviewer, not everyone
    client.get(f"/api/requests/{request_id}", headers=auth_headers(rev_token))

    # can't wait real days for this to go stale -- backdate it directly
    db = SessionLocal()
    req = db.query(ReimbursementRequest).filter(ReimbursementRequest.id == request_id).first()
    req.submitted_at = datetime.utcnow() - timedelta(days=5)
    db.commit()
    db.close()

    before_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    before_count = before_resp.json()["total"]

    trigger_resp = client.post("/api/admin/trigger-reminders", headers=auth_headers(admin_token))
    assert trigger_resp.status_code == 200
    assert trigger_resp.json()["reminders_sent"] == 1

    after_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    after_data = after_resp.json()
    assert after_data["total"] == before_count + 1
    assert "waiting" in after_data["items"][0]["message"]

    # triggering again immediately shouldn't re-remind (already reminded recently)
    second_trigger_resp = client.post("/api/admin/trigger-reminders", headers=auth_headers(admin_token))
    assert second_trigger_resp.json()["reminders_sent"] == 0

    no_new_notif_resp = client.get("/api/notifications", headers=auth_headers(rev_token))
    assert no_new_notif_resp.json()["total"] == after_data["total"]
