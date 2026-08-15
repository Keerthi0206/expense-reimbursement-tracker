Planning Document

Note: the original planning.md template provided in this repo was built for a different hackathon (it asked about ML model selection, detection categories, and precision/recall/F1 — shape of a PII-detection project). Those sections don't apply to a CRUD reimbursement tracker, so they've been replaced below with sections that match this project's actual requirements.

Tech Stack

Framework / Language: FastAPI (Python) backend, Next.js (App Router) frontend, SQLite database.

Why this stack: FastAPI gives automatic request validation via Pydantic and free OpenAPI docs, which matters for the "API design" and "documentation" rubric items. SQLite needs no setup for a 5-day window and the code reads DATABASE_URL from the environment, so moving to Postgres later is a config change. Next.js App Router keeps the requester/reviewer/detail pages organized by file-based routing without needing a separate router library.

Key libraries: SQLAlchemy (ORM), python-jose (JWT), passlib/bcrypt (password hashing), python-multipart (file uploads), pytest + httpx (testing).

Data Model
User: id, name, email, hashed_password, role (requester/reviewer/admin), is_active, created_at
ReimbursementRequest: id, title, amount, expense_date, category, description, status, requester_id, reviewer_id, receipt_filename/path, rejection_reason, reviewer_comment, timestamps
RequestHistory: append-only audit log of every action (create/submit/approve/reject/paid)
Notification: per-user, tied to a request, read/unread
Workflow & Status Design

Draft → Submitted → (Under Review, optional/merged with Submitted) → Approved/Rejected → Paid

Submitted and Under Review are treated as effectively the same reviewer-visible state per the hackathon's own guidance that these may be combined. Every transition is validated server-side: a request can't be approved twice, a rejected request can't be marked Paid, and a requester can never approve, reject, or pay their own request (enforced in the route handlers, not just hidden in the UI).

Roles
Requester: create/edit drafts, attach receipts, submit, view own requests + history
Reviewer: view all requests, approve/reject (with required reason)/mark paid, search/filter, dashboard
Admin: user management (API implemented; no UI built — see limitations)
Testing Plan

Automated pytest suite (backend/tests/test_workflow.py) covering: auth failures, field validation (negative amount, future date, missing category), the full create→paid happy path, rejection requiring a reason, cross-user access isolation, dashboard math, and search/filter. Manual smoke testing via curl against a live server for the exact "Minimum Demonstration Scenario" the hackathon lists, plus a full frontend build with zero errors and a live frontend-to-backend CORS/login check. See docs/testing.md for full results.

Phases & Priorities
Phase	Target Dates	Goals
1 — Plan & scaffold	Aug 14	Confirm data model, roles, repo structure, planning doc
2 — Requester flow	Aug 14–15	Auth, request form, validation, receipt upload, persistence
3 — Reviewer flow	Aug 15–16	Reviewer dashboard, approve/reject/paid, history, search/filter
4 — Secure & test	Aug 16–17	RBAC enforcement, dashboard totals, automated tests, seed data
5 — Polish & submit	Aug 17–19	Deploy, docs, walkthrough video, final submission check
What I'll Cut If Time Is Short

First to drop: the admin UI (API stays, no screen). Next: notifications UI (data still generated server-side). Last thing to cut: the core Create→Submit→Review→Approve/Reject→Paid workflow, backend validation, and RBAC — these are the 30%+10%+10% of the rubric that matter most and won't be sacrificed for polish.

Open Questions / Risks
Receipt storage on deploy: local disk storage won't persist across redeploys on most free hosting tiers. Mitigation: document this as a known limitation; object storage would be the production fix.
SQLite on Render's free tier: ephemeral filesystem could reset the DB on redeploy. Mitigation: reseed script is idempotent and fast; acceptable for a demo, flagged as a limitation for real use.
5-day timeline vs. Tier 2 stretch goals: prioritized a complete, tested Tier 1 over partial Tier 2 features, per the hackathon's own judging guidance.
