# CDF Expense & Reimbursement Tracker

**Live URL:** https://expense-reimbursement-tracker-three.vercel.app

A full-stack reimbursement tracker built for the CDF SDE Hackathon. Requesters create and submit expense requests with receipts; reviewers approve, reject or mark them paid; both sides can track status, search and filter. Built with FastAPI + SQLite on the backend and Next.js on the frontend.

## Features implemented

- Create → Submit → Review → Approve/Reject → Paid workflow, fully connected end to end
- Draft requests: save now, edit and finish later, a receipt is only required to submit, not to save a draft
- Reviewer "claim" flow: opening a submitted request moves it to Under Review; a `status=pending` filter alias keeps it visible in the review queue either way
- Request more information: a reviewer can send a submitted request back with a required message instead of approving or rejecting outright, the requester edits and resubmits it, cleanly modeled as its own status (`changes_requested`) not a bolt-on comment
- Approval reversal: a reviewer can reject an approved but unpaid request with a reason to correct a mistake locked out entirely once the request is Paid
- Cancel: a requester can cancel their own request any time before a reviewer approves or rejects it, with an optional reason implemented as a real `cancelled` status (not a hard delete), so the record and its history stay intact rather than disappearing from the audit trail
- Analytics & reporting: monthly spending trends, breakdowns by category and (for reviewers/admins) by requester, approval-time metrics, reviewer workload and CSV/PDF export, all role-scoped the same way as everything else (requesters only ever see their own data)
- Backend/API depth: real Alembic migrations (not just `create_all`) with indexes on every commonly-filtered column, an N+1 query bug found and fixed with real before/after query counts (19→2), `/api/v1/` versioning alongside the existing `/api/` paths, rate limiting (real 429s on repeated login attempts, verified live), request-ID + timing observability middleware, a real DB-connectivity health check, cursor-based (keyset) pagination alongside the existing page-based pagination, multi-value status filtering, `seed.py --reset`/`--scale` flags and a second scheduled background job (old read-notification cleanup) alongside the existing reminder job
- Receipt intelligence: real OCR (Tesseract, local - no external API key needed) reads amount/date/merchant off an uploaded receipt (image or PDF, including scanned PDFs) and offers them as suggestions on the New Request form - never auto-filled, the requester clicks to apply each one. Inline receipt thumbnails throughout, plus an on-demand consistency check on the detail page that flags if the submitted amount/date doesn't match what the receipt actually shows
- Light/dark theme, toggleable from the nav or login page, remembered across visits every color in the app comes from a shared token system, not hardcoded per component, so the whole UI (including status stamps, buttons and the always-dark topbar "cover") switches consistently rather than a partial reskin
- Every status transition (submit, approve, reject, mark paid, etc.) is a single atomic database update, not a read then write, verified safe against real concurrent requests (double-clicks, multiple tabs) not just sequential ones
- Backend enforced role-based access control (requester / reviewer / admin) - requesters cannot approve, reject or pay their own (or anyone's) requests
- Admin console: view all users (email, role, status, creation date), assign/change roles, activate/deactivate accounts, full audit history of who changed what and when and an admin can't change their own role or deactivate themselves
- Receipt upload with real content-type validation (checks file bytes, not just extension), 5MB limit, JPEG/PNG/PDF only
- Form + backend validation: amount > 0, no future dates, required fields, required rejection reason
- Full filtering, sorting (by date/amount/expense date/title, either direction) and pagination on the reviewer dashboard and status, category, requester, expense date range, amount range, keyword search
- Consistent, documented REST API (see `/docs` for live Swagger) covering users, requests, reviews, notifications and request history each with a dedicated endpoint including standalone `GET /api/requests/{id}/history` and `GET /api/admin/users/{id}/history` not just nested inside detail responses
- Server-side pagination on every list endpoint that can realistically grow requests, admin users, notifications and both history endpoints, all returning the same consistent shape (`items`/`page`/`page_size`/`total`/`total_pages`) with real Previous/Next navigation in the UI on the reviewer dashboard, admin page and notifications page
- Dashboard totals (requested / approved / pending / paid) and counts by status
- Full request history / audit trail
- In-app notifications on every meaningful status change including reviewers/admins getting notified the moment a new request is submitted, not just requesters being notified after someone acts on their request with a dedicated notifications page (unread badge in the nav, mark as read individually or all at once, links back to the related request)
- JWT auth, hashed passwords, secrets via environment variables, no stack traces leaked to the client
- Automated test suite (`backend/tests/`, 91 tests across `test_workflow.py`, `test_admin.py`, `test_email.py` and `test_error_handling_and_authorization.py`, covering the full reimbursement workflow, validation, RBAC, approval reversal, resubmission after rejection, cancellation, the two-tier approval workflow, duplicate-request detection, budget-limit warnings, receipt OCR extraction and consistency checks, request reminders, notification cleanup, cursor pagination, multi-value status filtering, rate limiting, the reviewer-claims-request transition, request-info/resubmission, admin user/role/status management with audit history, sorting and pagination on both list endpoints, the standalone request-history endpoint, a real concurrency race condition found and fixed during development, an N+1 query regression test, a route-ordering regression test and dedicated coverage of invalid-workflow-action prevention, unauthorized-action handling and graceful error handling including SQL-injection-style input)
- Fictional seed data covering every workflow state

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite (dev) / PostgreSQL (production see Deployment), python-jose (JWT), passlib/bcrypt
- **Frontend:** Next.js 14 (App Router), plain CSS (no UI framework)
- **Deploy target:** Render (backend) + Vercel (frontend)
- **Local dev:** run natively or `docker compose up --build` for one-command setup

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

### Docker (one command, both services)

```bash
cd backend
cp .env.example .env   # fill in real values if you want email, custom thresholds, etc.
cd ..
docker compose up --build
```

Backend at `http://localhost:8000`, frontend at `http://localhost:3000`. Uses SQLite by default (mounted to a named volume so data survives container restarts) and seeds demo data automatically on first run, no separate steps needed. `backend/.env` is optional (Docker Compose won't fail if it's missing) but creating it first is how you'd turn on real email delivery or change any of the other configurable thresholds see "Real email delivery" below. To use Postgres instead for closer production parity, swap `DATABASE_URL` in `docker-compose.yml` and add a `db` service (see the Deployment section below for the connection string format).

**Honest note:** this Docker setup was built and reasoned through carefully the exact runtime environment variables and startup command were verified against a real running server first and has since been run successfully in practice, including working through a real stale-database-schema issue after a mid-project schema change (fixed with `docker compose down -v` to clear the old volume). I still haven't run it myself in this development environment, which has no Docker daemon available but it's had genuine real-world use at this point not just a theoretical setup.

## Deployment

**Backend on Render — must use Render's free Postgres, not SQLite on disk.** Render's free web services don't support persistent disks (confirmed via Render's own docs), so a SQLite file would very likely not survive a restart or redeploy in production even though it works reliably for local development. Steps:

1. In Render, create a **PostgreSQL** instance (free tier - 1GB, expires after 30 days, which is fine for a hackathon submission window). Copy its **Internal Database URL**.
2. Create a **Web Service** pointing at this repo's `backend/` folder, build command `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. **Important:** Select Docker as the Runtime when creating the Render web service, not native Python, Render's native Python builds can't install system packages like `tesseract-ocr`, which the receipt-OCR feature needs. Point it at `backend/Dockerfile`.
4. Set environment variables on the web service: `DATABASE_URL` = the Postgres URL from step 1, `SECRET_KEY` = a long random string (not the dev default), `ALLOWED_ORIGINS` = your Vercel frontend URL.
5. Once deployed, open Render's shell for the service and run `python seed.py` once to create demo accounts and sample data.

This was verified end-to-end against a real local PostgreSQL instance (not just SQLite) before writing this section: all 91 backend tests pass against Postgres, a request created before a full server restart was still present afterward and the atomic status-transition race-condition fix (see `docs/testing.md`) was re-verified safe under Postgres's own locking not just SQLite's.

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

- Admin can create/view/manage users but there's no equivalent management UI for reimbursement-category configuration, categories are fixed in code (`CategoryEnum`) not admin-editable
- Receipts are stored on local disk under `backend/uploads/` not object storage. Fine for a demo; would move to S3/private bucket + signed URLs for production.
- Email notifications exist as a pluggable integration (off by default - see Features above) alongside the in-app notifications which work either way.
- SQLite is used for local development. **Production (Render) uses PostgreSQL instead**  Render's free web services don't support persistent disks, so a SQLite file wouldn't reliably survive a restart there. The code reads `DATABASE_URL` from the environment, so this is a config change not a code change see the Deployment section above. Tested against a real Postgres instance, including the full test suite and the concurrency-safety fix.

## Future improvements

- Cloud deployment, continuous deployment and monitoring: none of these were attempted, since they need real hosting/service accounts that made more sense to set up with someone present not rushed unattended
- Object storage (S3-compatible) with short-lived signed URLs for receipts, instead of local disk
- Optimistic UI updates on approve/reject so the reviewer doesn't wait on a full reload
- Admin-configurable reimbursement categories and budget thresholds instead of fixed in code
- Broader E2E coverage beyond the three critical-path tests currently there

See `docs/architecture.md`, `docs/testing.md` and `docs/reflection.md` for further detail.
