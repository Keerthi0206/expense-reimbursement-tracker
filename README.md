# CDF Expense & Reimbursement Tracker

**Live URL:** _add after deploying_

A full-stack reimbursement tracker built for the CDF SDE Hackathon. Requesters create and submit expense requests with receipts; reviewers approve, reject, or mark them paid; both sides can track status, search, and filter. Built with FastAPI + SQLite on the backend and Next.js on the frontend.

## Features implemented

- Create → Submit → Review → Approve/Reject → Paid workflow, fully connected end to end
- Draft requests: save now, edit and finish later — a receipt is only required to submit, not to save a draft
- Reviewer "claim" flow: opening a submitted request moves it to Under Review; a `status=pending` filter alias keeps it visible in the review queue either way
- Request more information: a reviewer can send a submitted request back with a required message instead of approving or rejecting outright — the requester edits and resubmits it, cleanly modeled as its own status (`changes_requested`), not a bolt-on comment
- Approval reversal: a reviewer can reject an approved-but-unpaid request with a reason to correct a mistake — locked out entirely once the request is Paid
- Every status transition (submit, approve, reject, mark paid, etc.) is a single atomic database update, not a read-then-write — verified safe against real concurrent requests (double-clicks, multiple tabs), not just sequential ones
- Backend-enforced role-based access control (requester / reviewer / admin) — requesters cannot approve, reject, or pay their own (or anyone's) requests
- Admin console: view all users (email, role, status, creation date), assign/change roles, activate/deactivate accounts, full audit history of who changed what and when — an admin can't change their own role or deactivate themselves
- Receipt upload with real content-type validation (checks file bytes, not just extension), 5MB limit, JPEG/PNG/PDF only
- Form + backend validation: amount > 0, no future dates, required fields, required rejection reason
- Full filtering, sorting (by date/amount/expense date/title, either direction), and pagination on the reviewer dashboard — status, category, requester, expense date range, amount range, keyword search
- Consistent, documented REST API (see `/docs` for live Swagger) covering users, requests, reviews, notifications, and request history, each with a dedicated endpoint — including standalone `GET /api/requests/{id}/history` and `GET /api/admin/users/{id}/history`, not just nested inside detail responses
- Server-side pagination on every list endpoint that can realistically grow — requests, admin users, notifications, and both history endpoints — all returning the same consistent shape (`items`/`page`/`page_size`/`total`/`total_pages`), with real Previous/Next navigation in the UI on the reviewer dashboard, admin page, and notifications page
- Dashboard totals (requested / approved / pending / paid) and counts by status
- Full request history / audit trail
- In-app notifications on status changes, with a dedicated notifications page (unread badge in the nav, mark-as-read individually or all at once, links back to the related request)
- JWT auth, hashed passwords, secrets via environment variables, no stack traces leaked to the client
- Automated test suite (`backend/tests/`, 54 tests across `test_workflow.py`, `test_admin.py`, and `test_error_handling_and_authorization.py`, covering the full reimbursement workflow, validation, RBAC, approval reversal, the reviewer-claims-request transition, request-info/resubmission, admin user/role/status management with audit history, sorting and pagination on both list endpoints, the standalone request-history endpoint, a real concurrency race condition found and fixed during development, and dedicated coverage of invalid-workflow-action prevention, unauthorized-action handling, and graceful error handling — including SQL-injection-style input)
- Fictional seed data covering every workflow state

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite (dev) / PostgreSQL (production — see Deployment), python-jose (JWT), passlib/bcrypt
- **Frontend:** Next.js 14 (App Router), plain CSS (no UI framework)
- **Deploy target:** Render (backend) + Vercel (frontend)

## Setup & run instructions

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                                # edit if needed
python seed.py                                       # creates demo data
uvicorn app.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### Frontend

```bash
cd src/frontend
cp .env.local.example .env.local                     # points at localhost:8000 by default
npm install
npm run dev
```

Visit `http://localhost:3000`.

### Tests

```bash
cd backend
pytest -v
```

## Deployment

**Backend on Render — must use Render's free Postgres, not SQLite on disk.** Render's free web services don't support persistent disks (confirmed via Render's own docs), so a SQLite file would very likely not survive a restart or redeploy in production, even though it works reliably for local development. Steps:

1. In Render, create a **PostgreSQL** instance (free tier — 1GB, expires after 30 days, which is fine for a hackathon submission window). Copy its **Internal Database URL**.
2. Create a **Web Service** pointing at this repo's `backend/` folder, build command `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Set environment variables on the web service: `DATABASE_URL` = the Postgres URL from step 1, `SECRET_KEY` = a long random string (not the dev default), `ALLOWED_ORIGINS` = your Vercel frontend URL.
4. Once deployed, open Render's shell for the service and run `python seed.py` once to create demo accounts and sample data.

This was verified end-to-end against a real local PostgreSQL instance (not just SQLite) before writing this section: all 49 backend tests pass against Postgres, a request created before a full server restart was still present afterward, and the atomic status-transition race-condition fix (see `docs/testing.md`) was re-verified safe under Postgres's own locking, not just SQLite's.

**Frontend on Vercel:** set `NEXT_PUBLIC_API_URL` to your Render backend's URL, deploy from `src/frontend`.

## Demonstration credentials

All demo accounts use password `password123`:

| Role      | Email                  |
|-----------|-------------------------|
| Requester | alice@example.com      |
| Requester | bob@example.com        |
| Reviewer  | rachel@example.com     |
| Admin     | admin@example.com      |

## Known limitations

- Admin can create/view/manage users but there's no equivalent management UI for reimbursement-category configuration — categories are fixed in code (`CategoryEnum`), not admin-editable
- Receipts are stored on local disk under `backend/uploads/`, not object storage. Fine for a demo; would move to S3/private bucket + signed URLs for production.
- No email notifications — in-app only (see Features above for the notifications page).
- SQLite is used for local development. **Production (Render) uses PostgreSQL instead** — Render's free web services don't support persistent disks, so a SQLite file wouldn't reliably survive a restart there. The code already reads `DATABASE_URL` from the environment, so this is a config change, not a code change — see the Deployment section above. Verified working against a real Postgres instance, including the full test suite and the concurrency-safety fix.

## Future improvements

- Admin UI for user management
- Notification bell / inbox in the frontend
- Editable drafts with autosave
- CSV export of the dashboard
- Docker Compose for one-command local setup

See `docs/architecture.md`, `docs/testing.md`, and `docs/reflection.md` for further detail.
