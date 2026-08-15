# Architecture Overview

## Final Tech Stack

| Layer     | Choice                                   | Why |
|-----------|-------------------------------------------|-----|
| Backend   | FastAPI (Python)                          | Async-friendly, automatic OpenAPI docs at `/docs`, strong typing via Pydantic for request validation |
| Database  | SQLite via SQLAlchemy ORM                 | Zero-setup persistence for a 5-day hackathon; `DATABASE_URL` is read from the environment so swapping to Postgres later is a config change, not a code change |
| Auth      | JWT (python-jose) + bcrypt password hashing | Stateless auth that's simple to reason about; no session store needed |
| Frontend  | Next.js 14 (App Router)                   | File-based routing kept the requester/reviewer/detail pages organized; React state (no external state library needed at this scale) |
| Styling   | Hand-written CSS (no framework)           | Small enough surface area that a utility framework wasn't worth the build complexity |

## Folder Structure

```
expense-tracker/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, global exception handlers
│   │   ├── core/
│   │   │   ├── database.py      # SQLAlchemy engine/session
│   │   │   ├── security.py      # JWT + password hashing + role guard dependency
│   │   │   └── files.py         # Receipt upload validation (magic-byte checking)
│   │   ├── models/models.py     # SQLAlchemy models: User, Request, History, Notification
│   │   ├── schemas/schemas.py   # Pydantic request/response schemas + validators
│   │   └── routers/
│   │       ├── auth.py          # Login, /me
│   │       ├── requests.py      # Core workflow: create/submit/approve/reject/paid/list/dashboard
│   │       ├── admin.py         # User management + role/status audit history
│   │       └── notifications.py
│   ├── seed.py                  # Fictional demo data covering every workflow state
│   └── tests/test_workflow.py   # Automated pytest suite
├── src/frontend/
│   ├── app/
│   │   ├── login/page.js
│   │   ├── requester/page.js        # Requester's request list
│   │   ├── requester/new/page.js    # Create + submit form
│   │   ├── reviewer/page.js         # Dashboard totals + review queue
│   │   └── requests/[id]/page.js    # Shared detail page (approve/reject/paid/history)
│   ├── components/               # StatusStamp, Nav, RequestRow
│   └── lib/                      # api.js (fetch wrapper), auth-context.js, require-auth.js
├── planning/planning.md
└── docs/
```

## Data Model

- **User**: id, name, email, hashed_password, role (requester/reviewer/admin), is_active
- **ReimbursementRequest**: id, title, amount, expense_date, category, description, status, requester_id, reviewer_id, receipt_filename/path, rejection_reason, reviewer_comment, info_requested_message, timestamps (created/updated/submitted/reviewed/paid)
- **RequestHistory**: append-only audit log — every create/submit/approve/reject/paid action is recorded with user, previous/new status, and comment
- **Notification**: per-user, tied to a request, with read/unread state
- **UserAccountHistory**: append-only audit log for admin actions on accounts — role changes and activate/deactivate events, recording who performed the action, the previous and new value, and when. Separate from `RequestHistory`, which tracks reimbursement-workflow actions, not account administration.

## Where the Model Runs

There is no ML model in this project — the "detection" work in the planning template doesn't apply here; see the note in `planning/planning.md`. All business logic (validation, status transitions, RBAC) runs synchronously in the FastAPI backend.

## Workflow Enforcement

Status transitions are enforced server-side, not just hidden in the UI:

- `draft → submitted`: requires a receipt to already be attached
- `submitted → under_review`: happens automatically when a reviewer/admin (never the owner) opens the request's detail page — this is what actually populates "Under Review" rather than leaving it as a status nothing transitions into. Idempotent: reopening an already-claimed request doesn't create duplicate history entries.
- `submitted/under_review → changes_requested`: a reviewer/admin can send a request back with a required message instead of approving or rejecting outright (`POST /request-info`), never the owner. The owner can then edit the request (same as editing a draft) and resubmit — which clears the message, logs a `resubmitted` history entry, and returns the request to `submitted`.
- `submitted/under_review → approved` or `rejected`: reviewer/admin only, and never the request's own owner
- `approved → rejected`: a reviewer can also reverse a mistaken approval (with a required reason) any time before payment; this is logged distinctly as `approval_revoked` in the history rather than a fresh rejection
- `rejected` requires a non-empty reason in both the initial-rejection and approval-reversal cases (Pydantic `min_length=1` + a 422 if missing); requesting more info requires a non-empty message the same way
- `approved → paid`: reviewer/admin only, never the owner. Once `paid`, the status is final — it cannot be rejected or reverted.
- Every transition writes a `RequestHistory` row
- **Every status transition is a single atomic, conditional database `UPDATE`** (`WHERE id = ... AND status IN (allowed statuses)`), not a Python read-then-write. This matters concretely: a naive "read the status, check it, then save" pattern has a real race — two simultaneous requests (a double-click, two open tabs, a retried network request) can both read the old status as still valid before either commits, and both "win." This was caught during manual concurrency testing (see `docs/testing.md`) and fixed for every transition endpoint (submit, approve, reject, request-info, mark-paid, and the reviewer-claims-request transition) — verified by firing 10 genuinely simultaneous requests at each and confirming exactly one succeeds.

The `GET /api/requests?status=pending` filter is a convenience alias covering both `submitted` and `under_review`, so a request doesn't disappear from a reviewer's default queue the moment they open (and thereby claim) it. `changes_requested` is deliberately excluded from "pending" and from the dashboard's `total_pending` figure, since at that point the request is waiting on the requester, not the reviewer — it still counts toward `total_requested` and has its own bucket in `count_by_status`.

## Admin Console

`/admin` (frontend) and `/api/admin/*` (backend), admin role only:

- View every user: name, email, role, active/inactive status, creation date (`GET /api/admin/users`)
- Create a new user with a role (`POST /api/admin/users`)
- Change a user's role (`PATCH /api/admin/users/{id}/role`) — an admin cannot change their own role, to prevent accidentally locking themselves out
- Activate or deactivate an account (`PATCH /api/admin/users/{id}/status`) — an admin cannot deactivate their own account; a deactivated user is blocked at login with a 403, not silently allowed through
- Every role change and activate/deactivate action writes a `UserAccountHistory` row (who did it, what changed from/to, when), viewable per-user via `GET /api/admin/users/{id}/history` and expandable inline on the admin page
- An admin also has reviewer permissions on reimbursement requests (approve/reject/mark paid/etc. all accept the admin role alongside reviewer) — the admin nav shows both "Review Queue" and "Admin"

## Security Notes

- Passwords are hashed with bcrypt, never stored or logged in plaintext
- JWTs carry the user id and role; `require_role()` is a FastAPI dependency that 403s before any handler code runs
- A global exception handler catches unhandled errors and returns a generic message + logs server-side, so stack traces and DB errors never reach the client
- Receipts are validated by magic bytes (first few bytes of the actual file), not by filename extension or client-supplied content-type, so a renamed `.exe` can't pass as a `.pdf`
- CORS is restricted to `ALLOWED_ORIGINS` from the environment (defaults to `localhost:3000` for local dev)

## What Changed From the Plan

The planning template itself was for a different (PII-detection) hackathon and was replaced up front with reimbursement-tracker-appropriate sections before development started — see `planning/planning.md`.

One real design decision changed after planning started: the original plan noted that Submitted and Under Review "may be combined," per the hackathon's own guidance that this is acceptable. During development this was replaced with an actual transition — a reviewer opening a submitted request now claims it as Under Review — because it gives the status real meaning (which requests have eyes on them vs. which are still waiting) rather than leaving it as a dead enum value that nothing ever produces.

A second addition made after initial development: the reviewer role description in the hackathon brief includes "Request additional information where implemented" — the "where implemented" wording suggests this is optional rather than a hard requirement, and it wasn't in the original build. It was added afterward as a proper `changes_requested` status (not a bolt-on comment field), reusing the same edit/resubmit path already built for drafts.

A third gap found by re-auditing against the brief: the Administrator role's backend endpoints (list/create users, change role, activate/deactivate) existed early on, but with no frontend at all — an admin logging in had nowhere to go and landed on the reviewer dashboard. A full `/admin` page was built afterward, along with the account-history audit trail the brief asks for ("View relevant role and account-status history"), which hadn't been built at all until this pass.

A fourth gap, same pattern: the brief lists "Status, Requester, Category, Date, Amount" as the filters a reviewer needs. The backend's `list_requests` endpoint always accepted `requester_id`, `date_from`, `date_to`, `min_amount`, and `max_amount` as query parameters, but the reviewer dashboard's UI only ever exposed Status, Category, and a keyword box — the other three were fully functional on the backend and simply invisible. Added a `GET /api/requests/meta/requesters` endpoint (reviewer/admin only, since reviewers can't hit the admin-only user list) to populate a requester dropdown, plus date-range and amount-range inputs on the reviewer page, wired to the params that already existed.

**The planning document's persistence risk turned out to be real, and was resolved rather than just documented.** `planning/planning.md` flagged that "SQLite on Render's free tier: ephemeral filesystem could reset the DB on redeploy" as an open risk, with reseeding as the mitigation. Confirmed via Render's own current documentation that free web services genuinely don't support persistent disks — this wasn't a hypothetical. Rather than accept data loss as a limitation, the fix was to use Render's free PostgreSQL tier for production instead of SQLite (the app already read `DATABASE_URL` from the environment, so no code changed, only deployment configuration). This was verified against a real local PostgreSQL instance, not assumed: all 49 backend tests pass against Postgres, a request created before a full server-process kill was confirmed still present after a completely fresh process started, and the atomic-transition race-condition fix (see `docs/testing.md`) was re-verified safe under Postgres's own locking behavior, not just SQLite's. See the README's Deployment section for the actual steps.

**A fifth gap found by re-auditing against the brief's API Design section**: three real inconsistencies. `GET /api/requests` had no sorting parameter at all — always hardcoded to `created_at desc` — despite the brief explicitly listing "Sorting" as an expected list-endpoint capability. `GET /api/admin/users` had no pagination whatsoever, returning every user unbounded, even though the brief lists "Users" specifically as a resource that should paginate. And request history was only ever accessible nested inside `GET /api/requests/{id}`'s response — there was no standalone `GET /api/requests/{id}/history` endpoint, which was inconsistent with `UserAccountHistory`'s own dedicated `GET /api/admin/users/{id}/history` endpoint built earlier in the same session. Fixed all three: added `sort_by`/`order` query params (whitelisted columns via a regex pattern, so an invalid column name returns a clean 422 instead of a server error) to the requests list; converted the admin users list to the same paginated response shape (`items`/`page`/`page_size`/`total`/`total_pages`) already used for requests, plus role/active-status filtering; and added `GET /api/requests/{id}/history` matching the admin pattern exactly. The admin users list becoming a paginated object instead of a bare array was a breaking response-shape change, so the frontend's `listUsers` call and the one component consuming it were updated in the same pass — verified by rebuilding and by live-testing the new shape against a running server.
