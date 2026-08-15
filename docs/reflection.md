# Reflection

## What I Built

A full-stack reimbursement tracker with a FastAPI backend (SQLite for local development, PostgreSQL in production) and a Next.js frontend, covering the complete Create → Submit → Review → Approve/Reject → Paid workflow with backend-enforced role-based access control for three roles (requester, reviewer, admin). Beyond the core workflow: draft save/edit, a "request more information" loop that sends a request back to the requester and lets them resubmit, approval reversal (a reviewer can undo a mistaken approval before payment), a full admin console with account role/status management and audit history, in-app notifications on every meaningful status change, receipt upload with real content-byte validation, and full search/filter/sort/pagination across every list endpoint. 57 automated backend tests, verified against both SQLite and a real PostgreSQL instance, plus a Docker Compose setup for one-command local startup.

## Key decisions and tradeoffs

- **SQLite for local dev, PostgreSQL for production**: SQLite needs zero setup for day-to-day development, but Render's free tier (where this deploys) doesn't support persistent disks, so a SQLite file wouldn't reliably survive a restart there. `DATABASE_URL` is read from the environment either way, so switching is a config change, not a code change — verified by running the full test suite and the concurrency-safety fix against a real local Postgres instance before relying on it.
- **JWT auth over sessions**: simpler to reason about for a small API, no session store needed. Tradeoff: no server-side revocation before expiry (12-hour token lifetime), which is an acceptable tradeoff for a hackathon demo but wouldn't be for production.
- **Hand-written CSS over a UI framework**: the app has a fixed, moderate set of screens, so a component library would have added setup overhead without much payoff. Traded some polish for controllable, purpose-built styling (the "ledger/stamp" visual language, distinct from a generic dashboard template).
- **Atomic database updates over read-then-write for status transitions**: found via manual concurrency testing that the original code (read the status, check it, write it back) had a real race — simultaneous requests could double-submit or double-approve. Every transition is now a single conditional `UPDATE` instead, checked against both SQLite and Postgres since they lock differently.
- **Magic-byte file validation**: receipts are checked by their actual file signature (first bytes), not filename extension or client-supplied MIME type, so a renamed executable can't be uploaded as a "receipt.pdf".
- **SQLite by default in the Docker setup, not Postgres**: keeps `docker compose up` to two services instead of three, with no database health-check timing to get wrong. Documented in `docker-compose.yml` how to swap to Postgres for anyone who wants production parity locally.

## What I'd Do Differently

- Add automated frontend tests (Playwright or similar) instead of relying on manual verification — this remains the one layer of the app without automated coverage
- Move receipt storage to object storage (S3-compatible) with short-lived signed URLs instead of local disk, for a real deployment — local disk is fine for a demo but wouldn't survive a redeploy on most hosts and doesn't match how a production system should handle files
- Add optimistic UI updates on approve/reject so the reviewer doesn't wait on a full reload
- Let an admin configure reimbursement categories instead of them being fixed in code
- Add CSV export of the dashboard and request list

## AI Tools Used

Claude (Anthropic) was used as a development assistant throughout: scaffolding the FastAPI backend structure, writing the SQLAlchemy models and Pydantic schemas, drafting the Next.js frontend pages and CSS, writing the automated pytest suite, and setting up the Docker configuration. All generated code was reviewed, run, and tested against a live server before being accepted — including catching and fixing several real bugs during manual testing: a JSON-serialization error in the validation exception handler, a genuine race condition in status transitions (found by firing concurrent requests at a running server, not just by inspection), a database-ordering bug where nested request history had no guaranteed chronological order (worked by accident on SQLite, not guaranteed on Postgres), and a test-isolation bug in the test suite itself where two test files shared one database engine due to Python's module-caching behavior. I made the architectural decisions (SQLite for dev vs. Postgres for prod, JWT vs. sessions, which Tier 2 items to attempt) and verified the security-sensitive logic myself — RBAC checks, file-type validation, password hashing, and the atomic-transition fix — by reading the code and testing it against real requests, including deliberately trying to break it (SQL-injection-style input, malformed JSON, disguised file uploads) rather than trusting it to be correct by construction.
