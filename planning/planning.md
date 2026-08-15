# Planning Document

> Note: the original `planning.md` template provided in this repo was built for a different
> hackathon (it asked about ML model selection, detection categories and precision/recall/F1
> shape of a PII-detection project). Those sections don't apply to a CRUD reimbursement tracker,
> so they have been replaced below with sections that match this project's actual requirements.

## Tech Stack

**Framework / Language:** FastAPI (Python) backend, Next.js (App Router) frontend, SQLite database.

**Why this stack:** FastAPI gives automatic request validation via Pydantic and free OpenAPI docs,
which matters for the "API design" and "documentation" rubric items. SQLite needs no setup for a
5-day window and the code reads `DATABASE_URL` from the environment, so moving to Postgres later
is a config change. Next.js App Router keeps the requester/reviewer/detail pages organized by
file-based routing without needing a separate router library.

**Key libraries:** SQLAlchemy (ORM), python-jose (JWT), passlib/bcrypt (password hashing),
python-multipart (file uploads), pytest + httpx (testing).

## Data Model

- **User**: id, name, email, hashed_password, role (requester/reviewer/admin), is_active, created_at
- **ReimbursementRequest**: id, title, amount, expense_date, category, description, status,
  requester_id, reviewer_id, receipt_filename/path, rejection_reason, reviewer_comment, timestamps
- **RequestHistory**: append-only audit log of every action (create/submit/approve/reject/paid)
- **Notification**: per-user, tied to a request, read/unread

## Workflow & Status Design

`Draft → Submitted → (Under Review, optional/merged with Submitted) → Approved/Rejected → Paid`

Submitted and Under Review are treated as effectively the same reviewer-visible state per the
hackathon's own guidance that these may be combined. Every transition is validated server-side:
a request can't be approved twice, a rejected request can't be marked Paid and a requester can
never approve, reject or pay their own request (enforced in the route handlers, not just hidden
in the UI).

## Roles

- **Requester**: create/edit drafts, attach receipts, submit, view own requests + history
- **Reviewer**: view all requests, approve/reject (with required reason)/mark paid, search/filter, dashboard
- **Admin**: user management (API implemented, no UI built, see limitations)

## Testing Plan

Automated pytest suite (`backend/tests/test_workflow.py`) covering: auth failures, field
validation (negative amount, future date, missing category), the full create→paid happy path,
rejection requiring a reason, cross-user access isolation, dashboard math and search/filter.
Manual smoke testing via curl against a live server for the exact "Minimum Demonstration
Scenario" the hackathon lists plus a full frontend build with zero errors and a live
frontend-to-backend CORS/login check. See `docs/testing.md` for full results.

## Phases & Priorities

| Phase | Target Dates | Goals |
|---|---|---|
| 1 - Plan & scaffold | Aug 14 | Confirm data model, roles, repo structure, planning doc |
| 2 - Requester flow | Aug 14-15 | Auth, request form, validation, receipt upload, persistence |
| 3 - Reviewer flow | Aug 15-16 | Reviewer dashboard, approve/reject/paid, history, search/filter |
| 4 - Secure & test | Aug 16-17 | RBAC enforcement, dashboard totals, automated tests, seed data |
| 5 - Tier 2 stretch | Aug 17-18 | Only after Tier 1 is complete and tested: pick a small number of Tier 2 items and go deep rather than wide, per the hackathon's own judging guidance |
| 6 - Polish & submit | Aug 18-19 | Deploy, docs, walkthrough video, final submission check |

Tier 2 items planned for Phase 5, in priority order: editable drafts with resubmission,
a detailed request/account history audit trail and a more complete automated test suite.
Each is a Tier 2 item that meaningfully strengthens the core workflow rather than adding an
unrelated feature, matching the hackathon's guidance that Tier 2 should build on a complete
Tier 1 not compensate for one.

## What I'll Cut If Time Is Short

**Tier 2 items are the first thing cut if time runs short** — they are explicitly optional per
the hackathon's own rules and a complete tested Tier 1 submission outscores a Tier 1 submission
with unfinished Tier 2 features bolted on. Within Tier 2, priority order if only some fit:
editable drafts/resubmission first (directly strengthens the core workflow), then the detailed
history audit trail, then the expanded test suite — CSV export, email notifications and a
Dockerized setup are the first three Tier 2 ideas to drop entirely.

Beyond Tier 2, every Tier 1 requirement — including Administrator functionality and
Notifications both listed under Tier 1 in the hackathon brief is treated as non-negotiable.
The full Tier 1 scope will be completed and tested before any further cuts are considered.

## Open Questions / Risks

- **Receipt storage on deploy**: local disk storage won't persist across redeploys on most free
  hosting tiers. Mitigation: document this as a known limitation; object storage would be the
  production fix.
- **SQLite on Render's free tier**: ephemeral filesystem could reset the DB on redeploy. Mitigation:
  reseed script is idempotent and fast; acceptable for a demo, flagged as a limitation for real use.
- **5-day timeline vs. Tier 2 stretch goals**: prioritized a complete, tested Tier 1 over partial
  Tier 2 features, per the hackathon's own judging guidance.
