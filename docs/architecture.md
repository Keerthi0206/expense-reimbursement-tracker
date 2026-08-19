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
- **RequestHistory**: append-only audit log every create/submit/approve/reject/paid action is recorded with user, previous/new status and comment
- **Notification**: per-user, tied to a request, with read/unread state
- **UserAccountHistory**: append-only audit log for admin actions on accounts role changes and activate/deactivate events, recording who performed the action, the previous and new value, an optional reason and when. Separate from `RequestHistory`, which tracks reimbursement-workflow actions, not account administration.

## Where the Model Runs

There is no ML model in this project the "detection" work in the planning template doesn't apply here; see the note in `planning/planning.md`. All business logic (validation, status transitions, RBAC) runs synchronously in the FastAPI backend.

## Workflow Enforcement

Status transitions are enforced server-side, not just hidden in the UI:

- `draft → submitted`: requires a receipt to already be attached
- `submitted → under_review`: happens automatically when a reviewer/admin (never the owner) opens the request's detail page this is what actually populates "Under Review" rather than leaving it as a status nothing transitions into. Idempotent: reopening an already-claimed request doesn't create duplicate history entries.
- `submitted/under_review → changes_requested`: a reviewer/admin can send a request back with a required message instead of approving or rejecting outright (`POST /request-info`), never the owner. The owner can then edit the request (same as editing a draft) and resubmit which clears the message, logs a `resubmitted` history entry and returns the request to `submitted`.
- `submitted/under_review → approved` or `rejected`: reviewer/admin only and never the request's own owner
- `approved → rejected`: a reviewer can also reverse a mistaken approval (with a required reason) any time before payment, this is logged distinctly as `approval_revoked` in the history rather than a fresh rejection
- `rejected` requires a non-empty reason in both the initial-rejection and approval-reversal cases (Pydantic `min_length=1` + a 422 if missing), requesting more info requires a non-empty message the same way
- `approved → paid`: reviewer/admin only, never the owner. Once `paid`, the status is final it cannot be rejected or reverted.
- Every transition writes a `RequestHistory` row
- **Every status transition is a single atomic, conditional database `UPDATE`** (`WHERE id = ... AND status IN (allowed statuses)`), not a Python read-then-write. This matters concretely: a naive "read the status, check it, then save" pattern has a real race, two simultaneous requests (a double-click, two open tabs, a retried network request) can both read the old status as still valid before either commits and both "win." This was caught during manual concurrency testing (see `docs/testing.md`) and fixed for every transition endpoint (submit, approve, reject, request-info, mark-paid and the reviewer-claims-request transition) verified by firing 10 genuinely simultaneous requests at each and confirming exactly one succeeds.

The `GET /api/requests?status=pending` filter is a convenience alias covering both `submitted` and `under_review`, so a request doesn't disappear from a reviewer's default queue the moment they open (and thereby claim) it. `changes_requested` is deliberately excluded from "pending" and from the dashboard's `total_pending` figure, since at that point the request is waiting on the requester, not the reviewer it still counts toward `total_requested` and has its own bucket in `count_by_status`.

## Admin Console

`/admin` (frontend) and `/api/admin/*` (backend), admin role only:

- View every user: name, email, role, active/inactive status, creation date (`GET /api/admin/users`)
- Create a new user with a role (`POST /api/admin/users`)
- Change a user's role (`PATCH /api/admin/users/{id}/role`) - an admin cannot change their own role, to prevent accidentally locking themselves out
- Activate or deactivate an account (`PATCH /api/admin/users/{id}/status`) - an admin cannot deactivate their own account; a deactivated user is blocked at login with a 403, not silently allowed through
- Every role change and activate/deactivate action writes a `UserAccountHistory` row (who did it, what changed from/to, when), viewable per-user via `GET /api/admin/users/{id}/history` and expandable inline on the admin page
- An admin also has reviewer permissions on reimbursement requests (approve/reject/mark paid/etc. all accept the admin role alongside reviewer) - the admin nav shows both "Review Queue" and "Admin"

## Security Notes

- Passwords are hashed with bcrypt, never stored or logged in plaintext
- JWTs carry the user id and role, `require_role()` is a FastAPI dependency that 403s before any handler code runs
- A global exception handler catches unhandled errors and returns a generic message + logs server-side, so stack traces and DB errors never reach the client
- Receipts are validated by magic bytes (first few bytes of the actual file), not by filename extension or client-supplied content-type, so a renamed `.exe` can't pass as a `.pdf`
- CORS is restricted to `ALLOWED_ORIGINS` from the environment (defaults to `localhost:3000` for local dev)

## What Changed From the Plan

The planning template itself was for a different (PII-detection) hackathon and was replaced up front with reimbursement-tracker-appropriate sections before development started - see `planning/planning.md`.

One real design decision changed after planning started: the original plan noted that Submitted and Under Review "may be combined", per the hackathon's own guidance that this is acceptable. During development this was replaced with an actual transition that is a reviewer opening a submitted request now claims it as Under Review because it gives the status real meaning (which requests have eyes on them vs. which are still waiting) rather than leaving it as a dead enum value that nothing ever produces.

A second addition made after initial development: the reviewer role description in the hackathon brief includes "Request additional information where implemented" - the "where implemented" wording suggests this is optional rather than a hard requirement and it wasn't in the original build. It was added afterward as a proper `changes_requested` status (not a bolt-on comment field), reusing the same edit/resubmit path already built for drafts.

A third gap found by re-auditing against the brief: the Administrator role's backend endpoints (list/create users, change role, activate/deactivate) existed early on, but with no frontend at all - an admin logging in had nowhere to go and landed on the reviewer dashboard. A full `/admin` page was built afterward, along with the account-history audit trail the brief asks for ("View relevant role and account-status history"), which hadn't been built at all until this pass.

A fourth gap, same pattern: the brief lists "Status, Requester, Category, Date, Amount" as the filters a reviewer needs. The backend's `list_requests` endpoint always accepted `requester_id`, `date_from`, `date_to`, `min_amount` and `max_amount` as query parameters, but the reviewer dashboard's UI only ever exposed Status, Category and a keyword box, the other three were fully functional on the backend and simply invisible. Added a `GET /api/requests/meta/requesters` endpoint (reviewer/admin only, since reviewers can't hit the admin-only user list) to populate a requester dropdown, plus date-range and amount-range inputs on the reviewer page wired to the params that already existed.

**The planning document's persistence risk turned out to be real and was resolved rather than just documented.** `planning/planning.md` flagged that "SQLite on Render's free tier: ephemeral filesystem could reset the DB on redeploy" as an open risk with reseeding as the mitigation. Confirmed via Render's own current documentation that free web services genuinely don't support persistent disks this wasn't a hypothetical. Rather than accept data loss as a limitation, the fix was to use Render's free PostgreSQL tier for production instead of SQLite (the app already read `DATABASE_URL` from the environment, so no code changed only deployment configuration). This was verified against a real local PostgreSQL instance, not assumed: all 49 backend tests pass against Postgres, a request created before a full server-process kill was confirmed still present after a completely fresh process started and the atomic-transition race-condition fix (see `docs/testing.md`) was re-verified safe under Postgres's own locking behavior, not just SQLite's. See the README's Deployment section for the actual steps.

**A fifth gap found by re-auditing against the brief's API Design section**: three real inconsistencies. `GET /api/requests` had no sorting parameter at all, always hardcoded to `created_at desc` despite the brief explicitly listing "Sorting" as an expected list-endpoint capability. `GET /api/admin/users` had no pagination whatsoever, returning every user unbounded even though the brief lists "Users" specifically as a resource that should paginate. And request history was only ever accessible nested inside `GET /api/requests/{id}`'s response there was no standalone `GET /api/requests/{id}/history` endpoint, which was inconsistent with `UserAccountHistory`'s own dedicated `GET /api/admin/users/{id}/history` endpoint built earlier in the same session. Fixed all three: added `sort_by`/`order` query params (whitelisted columns via a regex pattern, so an invalid column name returns a clean 422 instead of a server error) to the requests list; converted the admin users list to the same paginated response shape (`items`/`page`/`page_size`/`total`/`total_pages`) already used for requests, plus role/active-status filtering and added `GET /api/requests/{id}/history` matching the admin pattern exactly. The admin users list becoming a paginated object instead of a bare array was a breaking response-shape change, so the frontend's `listUsers` call and the one component consuming it were updated in the same pass, verified by rebuilding and by live-testing the new shape against a running server.

**A sixth gap found by re-auditing against the Notifications section**: every notification in the app was reactive a requester got notified after a reviewer approved, rejected, requested info or paid their request but nothing ever notified a *reviewer* that a new request existed in the first place. The brief's own wording, "generate a notification when important request statuses change", clearly covers Draft → Submitted, arguably the single most important transition from a reviewer's perspective, since it's what puts a request in front of them at all. Fixed by notifying every active reviewer and admin on a fresh (non-resubmission) submission there's no single assigned reviewer to target at that point, since `reviewer_id` stays null until someone claims or approves the request, so the notification goes to everyone who could act on it rather than one arbitrary person. Verified live against a running server with two separate accounts (a reviewer and an admin), both correctly received the notification and a permanent test (`test_submitting_a_request_notifies_active_reviewers_and_admins`) confirms the requester does not notify themselves in the process.

One more transition was checked and left as a deliberate judgment call before being reconsidered: the `submitted → under_review` "claim" transition (a reviewer opening a request) originally didn't notify the requester either. On reflection this genuinely fits "an important status changed" just as much as the others, so it was added — the requester now gets notified the moment their request is actually being looked at, not just when a final decision lands. Confirmed idempotent the same way the claim transition itself already was: reopening an already-claimed request doesn't fire a second notification (extended the existing `test_reviewer_opening_submitted_request_claims_it_as_under_review` test to check this directly, rather than adding a near-duplicate test).

**A seventh gap found by re-auditing against the Request History and Auditability section**: the brief lists six fields to record on a history entry — User, Action, Timestamp, Previous status, New status, Reason or comment — and `RequestHistory` already had all six. But `UserAccountHistory` (role changes and activate/deactivate events) only ever captured five of them: it had no `reason` column at all, and the admin API endpoints (`PATCH /users/{id}/role`, `PATCH /users/{id}/status`) didn't even accept one from the caller. There was no way to record *why* someone's role was changed or their account deactivated, even though the requests side of the app treated exactly that kind of context as a first-class field. Fixed by adding an optional `reason` field to both the database column and the two admin API schemas, threaded through to the history record, and shown in the admin page's history view when present. The frontend prompts for an optional reason via a simple dialog before either action — cancelling the prompt aborts the change entirely, leaving it blank proceeds without a reason, matching how an optional-but-encouraged field should behave. Verified live: deactivated a demo account with a reason through the real API and confirmed it round-tripped correctly into the history record, plus a permanent test (`test_reason_is_recorded_for_role_and_status_changes`) covering both the role-change and status-change cases.

**An eighth gap, more subtle than the others and worth explaining carefully**: the brief says a request should "provide a chronological history," but the `ReimbursementRequest.history` relationship had no `order_by` at all. The standalone `GET /api/requests/{id}/history` endpoint (added earlier) did sort explicitly, but the *nested* history returned inside `GET /api/requests/{id}` — the one the frontend detail page actually renders — relied on whatever order SQLAlchemy's default relationship loading happened to return. On SQLite this coincidentally matches insertion order in practice, which is why it "worked" and nobody noticed. It is not a guaranteed contract, and **PostgreSQL — the database this app is deployed with in production — makes no such guarantee for an unordered query**; this was a real production risk, not a hypothetical one, discovered only because the app happens to use two different databases for dev and prod. Fixed with `order_by="RequestHistory.timestamp"` on the relationship itself, so every consumer of `request.history` gets a guaranteed chronological order without needing to remember to sort it themselves.

Verifying this fix surfaced a second, smaller issue: a permanent test written to lock in the ordering (`test_nested_history_is_chronologically_ordered`) reuses the same shared test-user accounts as an existing test, `test_reviewer_opening_submitted_request_claims_it_as_under_review`. That existing test's assertion checked for a notification containing the substring `"under review"` — which is exactly the kind of message both tests now produce for the same shared account, since both exercise the claim-notification feature. Run in isolation each test passes; run together against Postgres specifically, the assertion started matching two notifications instead of one and failed — while SQLite happened not to expose it, illustrating exactly why testing against both databases mattered here, not just the one used for day-to-day development. Fixed by scoping that assertion to the specific `request_id` under test rather than a message substring, which is what it should have done from the start.

**A ninth gap found by re-auditing against Setup and Developer Experience**: the brief says "a Dockerized local setup is strongly encouraged," and no Docker configuration existed anywhere in the repo — a genuine gap, not just an unstarted stretch goal, given the strength of that wording. Added `backend/Dockerfile`, `src/frontend/Dockerfile`, `.dockerignore` for both, and a root `docker-compose.yml` that brings up both services with one command. Deliberately defaults to SQLite rather than Postgres for the Docker setup specifically — it keeps the compose file to two services instead of three, with no database health-check timing to potentially get wrong — with the tradeoff (not matching production's database) documented directly in the compose file's comments, and a note on how to switch to Postgres for anyone who wants that parity locally. One honest limitation on this specific piece: this development environment has no Docker daemon available, so the compose file's *logic* was verified carefully (confirmed the exact SQLite absolute-path URL format resolves correctly via SQLAlchemy directly, then ran the actual seed script and server with the identical environment variables and startup command the container will use, confirming login and health-check work end to end) but the Docker build itself was never actually executed. That's a meaningfully weaker form of verification than everything else in this document, and it's called out as such directly in the README rather than presented as equally solid.

This pass also caught `docs/reflection.md` had drifted out of date in the same way it had once before mid-project — it still described "no admin UI" as a current design tradeoff and listed both the admin UI and a notifications inbox under "what I'd do differently," despite both being fully built by this point. Rewritten to reflect the app's actual final state, and the README's "Future improvements" list (which had the identical problem — it listed Docker, the admin UI, and the notifications inbox as *not yet done*, all three of which now exist) was corrected the same way.

## Cancel requests

Added after the core build, on request: a requester can cancel their own request any time before a reviewer approves or rejects it. The obvious implementation of "delete" — actually removing the row from the database — was deliberately not what got built, since it would contradict everything in the Request History and Auditability section: a deleted request has no history, no audit trail, nothing for a reviewer to ever see if they'd already been notified about it. Instead, `cancelled` is a real status, same tier as `approved` or `rejected` — the record, its full history, and the reason (if given) all stay intact. Reuses the same atomic-transition pattern as every other status change, so it's race-safe by construction rather than needing a separate fix later. If a reviewer had already claimed the request, they're notified that it was cancelled, same as every other meaningful status change in the app. Dashboard totals exclude cancelled requests from `total_requested`, matching how drafts are already excluded — a cancelled request was never really "requested" in the sense that number is meant to track.

## Two-Tier Approval and Workflow Rules

Requests over $500 (configurable), or in the `training` category regardless of amount, need a second approval from an admin after the first reviewer approval — a `pending_second_approval` status sits between `submitted` and `approved`. The rule lives in one small module (`app/core/workflow_rules.py`) instead of scattered conditionals, and the backend blocks the same person from giving both approvals, plus requires the second one specifically come from an admin, not just any reviewer.

## Receipt Intelligence

Tesseract handles OCR (it's a system dependency in the backend Dockerfile — `pytesseract` alone is just a Python wrapper, it needs the actual binary present). Images go straight through Tesseract; PDFs try their embedded text layer first, which is faster and exact for a digitally-generated invoice, and only fall back to rendering the page and OCRing it if there's no usable text layer, which covers scanned PDFs. Every extracted value comes back as a suggestion — the New Request form never fills a field on its own, the requester has to click to apply it. A separate on-demand endpoint re-runs extraction against an already-submitted request's stored receipt and flags it if the submitted amount or date doesn't line up.

## Backend and API Depth

- Alembic migrations instead of `Base.metadata.create_all`, run automatically on startup by both the server and `seed.py` — whichever runs first wins, the other is a no-op. Indexes on the columns that actually get filtered on (`status`, `requester_id`, `expense_date`) ship as a second migration.
- Cursor-based pagination (`GET /api/requests/cursor`) alongside the existing page-based pagination, keyset-ordered by `(created_at, id)` so results don't shift if rows change between page loads.
- Every route is reachable at both `/api/...` and `/api/v1/...`.
- Login is rate limited (20 attempts/minute per IP).
- Every request gets a structured JSON log line with a request ID and timing, and that same ID comes back to the client on a 500 error so a bug report can be traced to a specific log entry.

## Analytics and Reporting

Monthly totals, category and requester breakdowns, approval-time stats, and reviewer workload, computed in `app/core/analytics.py` from a single eager-loaded query. The first version accessed `request.requester.name` in a loop with no eager loading — a classic N+1 pattern, caught by measuring query counts directly (19 queries for 15 distinct requesters, down to 2 after adding `joinedload`). CSV and PDF export reuse the same role-scoped query the charts use, so an export can't leak another requester's data.

## Accessibility

Every error banner announces to screen readers and grabs keyboard focus when it appears, through one shared hook instead of duplicated logic per page. Form fields link to their errors with `aria-describedby` and `aria-invalid`. Two bugs came out of this pass: a clickable receipt thumbnail had no keyboard path to it at all (fixed by wrapping it in a `<button>`), and the admin page's "Loading users…" state was indistinguishable from a zero-result search, so a search with no matches looked stuck loading forever.

## Testing and CI

87 backend tests, plus 3 Playwright end-to-end tests that run against a real browser and real running servers, covering login/role-redirects, draft creation, and the full requester-submits → reviewer-approves flow. `.github/workflows/ci.yml` runs backend lint and tests, frontend lint and build, and the E2E suite on every push. Both linters caught real issues the first time I ran them, including a misconfigured `pyproject.toml` that was silently letting ruff run its full default rule set instead of the one I actually wanted.
