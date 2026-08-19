# Reflection

## What I Built

A full-stack reimbursement tracker: FastAPI backend (SQLite locally, PostgreSQL in production), Next.js frontend, the full Create → Submit → Review → Approve/Reject → Paid workflow, with backend-enforced role-based access for requesters, reviewers, and admins.

Past the core Tier 1 workflow, I picked a handful of Tier 2 categories and went deep on them instead of spreading thin across all of them:

- **Workflow depth**: resubmission after rejection, duplicate-request detection, budget-limit warnings, a two-tier approval flow (high-value or training-category requests need a second sign-off from an admin), scheduled reminders and notification cleanup, and email notifications built as an optional integration that's off by default.
- **Receipt intelligence**: Tesseract OCR (local, no external API) reads amount/date/merchant off an uploaded receipt — image or PDF, scanned or not — and offers them as suggestions the requester clicks to apply, never auto-filled. A consistency check on the detail page re-reads the stored receipt and flags it if the submitted amount or date doesn't match.
- **Analytics**: monthly trends, category and requester breakdowns, approval-time stats, reviewer workload, CSV/PDF export.
- **Backend/API depth**: Alembic migrations instead of `create_all`, indexes on the columns that actually get filtered on, cursor pagination alongside page-based, `/api/v1/` versioning, rate limiting, structured JSON logging, and a health check that actually pings the database.
- **Accessibility**: screen-reader support, keyboard reachability, focus management on errors, mobile-responsive layouts and charts, URL-persisted filters.
- **Testing & CI**: 87 backend tests, 3 Playwright E2E tests, both linters wired into a GitHub Actions pipeline that runs on every push.

## Key decisions and tradeoffs

- **SQLite locally, Postgres in production** — `DATABASE_URL` comes from the environment either way, so it's a config switch, not a code change. I tested the concurrency fix below against an actual Postgres instance rather than assuming SQLite behavior would carry over.
- **Alembic over `create_all`** — I hit this the hard way mid-project: a schema change broke an existing local database with no way to fix it short of wiping it. Migrations give you an upgrade path instead. I tested both directions, up and down, before trusting it.
- **JWT over sessions** — simpler for a small API, no session store to run. The tradeoff is no server-side revocation before the token expires, which is fine for a demo and wouldn't be for production.
- **Atomic updates instead of read-then-write for status changes** — concurrency testing turned up a race where two simultaneous requests could double-approve the same thing. Every transition is a single conditional `UPDATE` now.
- **OCR stays a suggestion, never auto-fills** — the brief asked for this, and it's the right call anyway: accuracy depends a lot on image quality (I tested this directly — a rough bitmap font garbled several characters, a clean font was perfect), so treating it as a suggestion rather than a fact is the honest way to build it.
- **The second-approval rule lives in one small module**, not scattered if-statements, so "which requests need a second sign-off" is a single policy decision you can point to.
- **Email is pluggable, not required** — it's a working integration (it does attempt SMTP and fails gracefully without credentials), but nothing in the app depends on it, since I don't have real credentials to test actual delivery with.

## What I'd Do Differently

- Didn't attempt cloud deployment or CD — both need real hosting accounts, and that felt like something to set up with the person actually running the demo, not to rush through unattended
- Skipped monitoring (Sentry or similar) for the same reason — needs a real account to be worth more than a stub
- Receipt storage should move to something like S3 with signed URLs for an actual deployment; local disk is fine for a demo
- Categories and budget thresholds are fixed in code — an admin should be able to configure those
- E2E coverage is currently three critical-path tests; there's room to grow that

## AI Tools Used

I used Claude throughout — scaffolding the backend and frontend, writing tests, working through each Tier 2 area. I ran and checked the output rather than taking it on faith: measured actual query counts to confirm an N+1 fix worked (19 down to 2), caught a route-ordering bug by hitting the endpoint before it shipped, tested the migration path in both directions against a live database file, and found a logging bug — Alembic's own setup was quietly overriding the app's — by looking at what the logs actually printed, not by assuming the code was right. I made the calls on what to prioritize given the timeline, the two-tier approval design, and SQLite vs. Postgres, and went through the security-sensitive pieces myself — RBAC, file validation, rate limiting, the atomic-transition fix — including trying to break them on purpose rather than trusting they'd hold up.
