"""
Automated tests for admin user management: listing, role/status changes,
self-protection guards, and the account-history audit trail.

Run with: pytest -v
"""
import os
import sys

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
