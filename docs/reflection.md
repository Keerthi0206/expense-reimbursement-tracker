# Reflection

## What I Built

A full-stack reimbursement tracker with a FastAPI + SQLite backend and a Next.js frontend, covering the complete Create → Submit → Review → Approve/Reject → Paid workflow with backend-enforced role-based access control, receipt upload with real content validation, search/filter/pagination, dashboard totals, and a full audit history per request.

## Key decisions and tradeoffs

- **SQLite over Postgres**: faster to get running for a 5-day window with zero external setup. `DATABASE_URL` is read from the environment so this is a one-line change to move to Postgres later, not a rewrite.
- **JWT auth over sessions**: simpler to reason about for a small API, no session store needed. Tradeoff: no server-side revocation before expiry (12-hour token lifetime), which is an acceptable tradeoff for a hackathon demo but wouldn't be for production.
- **Hand-written CSS over a UI framework**: the app has a small, fixed set of screens, so a component library would have added setup overhead without much payoff. Traded some polish for controllable, purpose-built styling (the "ledger/stamp" visual language, distinct from a generic dashboard template).
- **No admin UI**: the admin API (user list, role/status changes) is implemented and tested, but I prioritized the core requester/reviewer workflow first since that's 30% of the rubric and the admin role isn't part of the minimum workflow per the hackathon brief. Documented as a known limitation.
- **Magic-byte file validation**: receipts are checked by their actual file signature (first bytes), not filename extension or client-supplied MIME type, so a renamed executable can't be uploaded as a "receipt.pdf".

## What I'd Do Differently

- Add an admin UI rather than leaving it API-only
- Add a notifications inbox in the frontend (the backend already generates and stores them)
- Add Playwright tests for the frontend instead of relying on manual verification
- Move receipt storage to object storage (S3-compatible) with short-lived signed URLs instead of local disk, for a real deployment
- Add optimistic UI updates on approve/reject so the reviewer doesn't wait on a full reload

## AI Tools Used

Claude (Anthropic) was used as a development assistant throughout: scaffolding the FastAPI backend structure, writing the SQLAlchemy models and Pydantic schemas, drafting the Next.js frontend pages and CSS, and writing the automated pytest suite. All generated code was reviewed, run, and tested against a live server before being accepted — including catching and fixing a real bug (a JSON-serialization error in the validation exception handler when a Pydantic custom validator's `ValueError` was included directly in the error response) during manual smoke testing. I made the architectural decisions (SQLite vs. Postgres, JWT vs. sessions, no admin UI for v1) and verified the security-sensitive logic (RBAC checks, file-type validation, password hashing) myself by reading the code and testing it against real requests rather than trusting it to be correct by construction.
