# Walkthrough Video

**Video Link:** _add before submission_

## What to cover (3-5 minutes)

- What you built and the tech stack (FastAPI + SQLite backend, Next.js frontend)
- Requester workflow: create a request, trigger a validation error (negative amount or missing receipt), attach a receipt, submit
- Reviewer workflow: view the queue, approve one request, reject another with a reason, mark an approved request as Paid
- Search/filter the request list
- Dashboard totals
- How data is stored (SQLite via SQLAlchemy) and how receipts are protected (magic-byte validation, access restricted to the owner + reviewers/admins)
- How roles are enforced (backend `require_role` dependency — demonstrate a 403 when a requester tries a reviewer action)
- Known limitations and what you'd improve next (see `docs/reflection.md`)
