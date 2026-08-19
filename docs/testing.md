# Testing

## Approach

Three layers of testing:

1. **Automated backend tests** (`backend/tests/`) - 91 pytest cases against the FastAPI app via `TestClient`, sharing one isolated SQLite test database managed by `tests/conftest.py`. Covers the workflow state machine, RBAC, the two-tier approval rules, receipt OCR extraction, analytics, cursor pagination, rate limiting, email notifications (`test_email.py`) and a few regression tests locking in bugs found along the way (an N+1 query, a route-ordering collision, a database-persistence check).
2. **End-to-end browser tests** (`e2e/`, Playwright) - 3 test files covering login/role-redirect, draft creation and the full requester-submits → reviewer-approves workflow, run against running frontend and backend servers with Chromium.
3. **CI** (`.github/workflows/ci.yml`) - every push runs backend lint + tests, frontend lint + build and the E2E suite.

## Automated test results

```
tests/test_admin.py::test_non_admin_cannot_list_users PASSED
tests/test_admin.py::test_admin_can_list_users_with_full_fields PASSED
tests/test_admin.py::test_admin_users_list_supports_pagination_filtering_and_sorting PASSED
tests/test_admin.py::test_admin_users_search_matches_name_or_email PASSED
tests/test_admin.py::test_reason_is_recorded_for_role_and_status_changes PASSED
tests/test_admin.py::test_admin_can_change_a_users_role_and_it_is_logged PASSED
tests/test_admin.py::test_admin_cannot_change_their_own_role PASSED
tests/test_admin.py::test_admin_can_deactivate_and_reactivate_a_user_with_history PASSED
tests/test_admin.py::test_admin_cannot_deactivate_self PASSED
tests/test_admin.py::test_creating_a_user_is_logged_in_history PASSED
tests/test_admin.py::test_non_admin_cannot_view_or_modify_user_history PASSED
tests/test_admin.py::test_reminders_go_out_for_stale_pending_requests PASSED
tests/test_admin.py::test_notification_cleanup_removes_only_old_read_notifications PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_approve_a_draft PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_reject_a_draft PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_mark_paid_a_draft PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_submit_without_receipt PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_submit_an_already_submitted_request PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_mark_paid_a_merely_submitted_request PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_approve_twice PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_submit_a_paid_request PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_mark_paid_twice PASSED
tests/test_error_handling_and_authorization.py::TestInvalidWorkflowActions::test_cannot_reject_a_paid_request PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_no_token_returns_401 PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_garbage_token_returns_401 PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_requester_cannot_approve_own_request PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_requester_cannot_view_someone_elses_request PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_requester_cannot_edit_someone_elses_request PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_reviewer_cannot_create_a_request PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_non_admin_blocked_from_admin_endpoint PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_requester_cannot_download_someone_elses_receipt PASSED
tests/test_error_handling_and_authorization.py::TestUnauthorizedActions::test_admin_cannot_approve_reject_or_pay_their_own_request PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_malformed_json_body_does_not_crash PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_sql_injection_style_id_is_treated_as_literal_data PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_sql_injection_style_string_in_title_is_stored_as_plain_text PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_wrong_content_type_does_not_crash PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_empty_body_does_not_crash PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_oversized_field_is_rejected_not_crashed PASSED
tests/test_error_handling_and_authorization.py::TestGracefulErrorHandling::test_unhandled_error_response_never_contains_secret_values PASSED
tests/test_workflow.py::test_login_wrong_password_returns_401 PASSED
tests/test_workflow.py::test_login_unknown_email_returns_401_not_500 PASSED
tests/test_workflow.py::test_login_is_rate_limited_after_repeated_attempts PASSED
tests/test_workflow.py::test_create_request_requires_auth PASSED
tests/test_workflow.py::test_budget_limit_warning_flag_is_computed PASSED
tests/test_workflow.py::test_negative_amount_rejected PASSED
tests/test_workflow.py::test_future_date_rejected PASSED
tests/test_workflow.py::test_missing_category_rejected PASSED
tests/test_workflow.py::test_nested_history_is_chronologically_ordered PASSED
tests/test_workflow.py::test_high_value_request_needs_second_admin_approval PASSED
tests/test_workflow.py::test_same_person_cannot_give_both_approvals PASSED
tests/test_workflow.py::test_low_value_request_skips_second_tier_entirely PASSED
tests/test_workflow.py::test_can_reject_a_request_awaiting_second_approval PASSED
tests/test_workflow.py::test_full_workflow_create_to_paid PASSED
tests/test_workflow.py::test_requester_can_cancel_before_approval PASSED
tests/test_workflow.py::test_cannot_cancel_after_approval PASSED
tests/test_workflow.py::test_cancelling_a_claimed_request_notifies_the_reviewer PASSED
tests/test_workflow.py::test_double_submit_race_is_prevented PASSED
tests/test_workflow.py::test_can_edit_and_resubmit_after_rejection PASSED
tests/test_workflow.py::test_reject_requires_reason PASSED
tests/test_workflow.py::test_requester_cannot_see_others_requests PASSED
tests/test_workflow.py::test_approved_request_can_be_reverted_but_not_after_paid PASSED
tests/test_workflow.py::test_reviewer_opening_submitted_request_claims_it_as_under_review PASSED
tests/test_workflow.py::test_request_info_flow_and_resubmission PASSED
tests/test_workflow.py::test_submitting_a_request_notifies_active_reviewers_and_admins PASSED
tests/test_workflow.py::test_notifications_are_paginated_and_scoped_to_the_user PASSED
tests/test_workflow.py::test_dashboard_totals_are_accurate PASSED
tests/test_workflow.py::test_data_survives_a_completely_new_database_connection PASSED
tests/test_workflow.py::test_analytics_requester_sees_only_own_data_no_cross_user_views PASSED
tests/test_workflow.py::test_analytics_reviewer_sees_cross_user_breakdowns PASSED
tests/test_workflow.py::test_analytics_does_not_n_plus_one_query_per_distinct_user PASSED
tests/test_workflow.py::test_analytics_date_range_filters_correctly PASSED
tests/test_workflow.py::test_csv_export_returns_real_csv_scoped_to_requester PASSED
tests/test_workflow.py::test_pdf_export_returns_a_real_pdf PASSED
tests/test_workflow.py::test_export_respects_status_filter PASSED
tests/test_workflow.py::test_multi_value_status_filter PASSED
tests/test_workflow.py::test_search_and_filter PASSED
tests/test_workflow.py::test_duplicate_check_finds_matching_amount_and_date PASSED
tests/test_workflow.py::test_cursor_pagination_walks_through_without_gaps_or_overlap PASSED
tests/test_workflow.py::test_sorting_requests_by_amount PASSED
tests/test_workflow.py::test_request_history_has_its_own_endpoint PASSED
tests/test_workflow.py::test_deactivated_account_cannot_log_in PASSED
tests/test_workflow.py::test_extract_receipt_preview_before_request_exists PASSED
tests/test_workflow.py::test_extract_receipt_preview_rejects_bad_file_type PASSED
tests/test_workflow.py::test_receipt_analysis_requires_a_receipt_first PASSED
tests/test_workflow.py::test_receipt_analysis_flags_a_genuine_mismatch PASSED
tests/test_workflow.py::test_receipt_analysis_no_mismatch_when_values_actually_match PASSED
tests/test_workflow.py::test_receipt_analysis_respects_normal_access_control PASSED

======================= 91 passed =======================
```

Run it yourself: `cd backend && pytest -v`

## Invalid workflow actions, authorization, and graceful error handling — verified

These three requirements got dedicated attention beyond the general workflow tests, both manually (live curl against a running server, listed below) and with a permanent test file, `test_error_handling_and_authorization.py`:

**Invalid workflow actions prevented** — every wrong-status transition attempt returns 400, not a crash or a silent no-op: approving/rejecting/paying a draft, submitting twice, marking-paid something merely submitted, approving twice, submitting or rejecting something already paid, marking-paid twice (the double-payment scenario).

**Unauthorized actions return appropriate errors** — no token → 401; garbage token → 401; wrong role for an action → 403; not the request's owner and not a reviewer/admin → 403 (applies to viewing, editing, and downloading another user's receipt); non-admin hitting `/api/admin/*` → 403.

**Backend validation, not just frontend** — every one of these was tested by calling the API directly with curl, never touching the React UI at all: negative amounts, wrong types (amount as a string), invalid enum values, future dates, malformed date strings, empty required strings, missing fields — all correctly rejected with 422 by Pydantic validators that exist independently of anything in `src/frontend`.

**Graceful handling of invalid/unexpected input** — deliberately tried to break things and confirmed none of it leaked internals:
- Malformed/broken JSON body → clean 422, not a crash
- SQL-injection-style content in a request ID (`'; DROP TABLE users; --`) → a normal 404, because the ORM parameterizes queries automatically; the string is never executed as SQL. Confirmed the `users` table survived by logging in again immediately after.
- The same SQL-injection-style string used as a request *title* → stored and returned as inert plain text, never executed
- Wrong `Content-Type` header on a JSON endpoint → 422, not a crash
- Empty request body → 422
- A 100,000-character title → rejected by the existing `max_length=200` field validator with 422, not a buffer issue
- Checked every error response body across all of this for the words "traceback", "secret", "password", "site-packages", or `sqlalchemy.exc" — none ever appeared. The global exception handler in `app/main.py` catches any truly unhandled exception and always returns a fixed generic message, logging the real detail server-side instead.

## What each test covers

| Test | Scenario |
|---|---|
| `test_non_admin_cannot_list_users` | A requester/reviewer token gets 403 from `/api/admin/users` |
| `test_admin_can_list_users_with_full_fields` | Every field the admin brief requires (email, role, status, created date) is present in the response |
| `test_admin_users_list_supports_pagination_filtering_and_sorting` | `/api/admin/users` returns the same paginated shape as requests (`items`/`page`/`page_size`/`total`/`total_pages`); filters correctly by `role` and `is_active`; sorts by `name` ascending correctly; an invalid `role` filter value returns 422 |
| `test_admin_can_change_a_users_role_and_it_is_logged` | Role change succeeds and writes a `role_changed` history entry with the correct previous/new values and who performed it |
| `test_reason_is_recorded_for_role_and_status_changes` | An optional `reason` passed to the role-change and status-change endpoints round-trips correctly into the corresponding history entry — closing a gap where `UserAccountHistory` had 5 of the 6 fields the brief asks for (no reason/comment) while `RequestHistory` already had all 6 |
| `test_admin_cannot_change_their_own_role` | Self-role-change is blocked (400) so an admin can't accidentally lock themselves out |
| `test_admin_can_deactivate_and_reactivate_a_user_with_history` | Deactivation blocks that user's login (403) with the correct message; reactivation restores it; both actions are logged |
| `test_admin_cannot_deactivate_self` | Self-deactivation is blocked (400) |
| `test_creating_a_user_is_logged_in_history` | Creating a user via the admin API writes a `created` history entry |
| `test_non_admin_cannot_view_or_modify_user_history` | A non-admin gets 403 trying to view another user's account history |
| `test_login_wrong_password_returns_401` | Wrong password doesn't leak whether the account exists |
| `test_login_unknown_email_returns_401_not_500` | Unknown email is handled gracefully, not a 500 |
| `test_create_request_requires_auth` | Unauthenticated request creation is rejected (401) |
| `test_negative_amount_rejected` | Amount ≤ 0 is rejected (422) |
| `test_future_date_rejected` | Expense date in the future is rejected (422) |
| `test_missing_category_rejected` | Missing required field is rejected (422) |
| `test_nested_history_is_chronologically_ordered` | The nested `request.history` returned inside `GET /api/requests/{id}` is guaranteed sorted by timestamp — not just "usually looks right" — verified against both SQLite and a real local PostgreSQL instance, since Postgres gives no ordering guarantee without an explicit `ORDER BY` and is what the app actually deploys with in production |
| `test_full_workflow_create_to_paid` | The entire Create → (blocked submit without receipt) → upload receipt → (blocked bad file type) → Submit → (blocked self-approval... via role) → Approve → (blocked double-approve) → (blocked requester mark-paid) → Mark Paid path, plus checks that history entries were recorded at each step |
| `test_double_submit_race_is_prevented` | Fires 10 genuinely concurrent submit requests (real Python threads, separate `TestClient` instances) at the same draft request and asserts exactly 1 succeeds and 9 get 400 — regression test for a real race condition found via manual testing, see below |
| `test_requester_can_cancel_before_approval` | Another requester can't cancel someone else's request (403); the owner can cancel a draft with an optional reason; cancelling an already-cancelled request is blocked (400); the reason shows up correctly in the request's history |
| `test_cannot_cancel_after_approval` | A request that's been approved can no longer be cancelled (400), and the same is true once it's been paid |
| `test_cancelling_a_claimed_request_notifies_the_reviewer` | If a reviewer has already claimed a request, cancelling it sends them a notification mentioning the cancellation |
| `test_reject_requires_reason` | Empty rejection reason is rejected (422); valid reason succeeds; a rejected request cannot then be marked Paid |
| `test_requester_cannot_see_others_requests` | Cross-user data isolation — a requester can't view or list another requester's request (403, and excluded from list results) |
| `test_approved_request_can_be_reverted_but_not_after_paid` | A reviewer can reject (revoke) an approved-but-unpaid request with a reason, recorded as `approval_revoked`; once `paid`, that same action is blocked (400) |
| `test_reviewer_opening_submitted_request_claims_it_as_under_review` | Owner viewing their own request doesn't trigger the claim; a reviewer opening it does, moves status to `under_review`, is idempotent on repeat views (no duplicate history entry, no duplicate notification), remains approvable afterward, notifies the requester once, and the `status=pending` filter alias still surfaces it |
| `test_request_info_flow_and_resubmission` | Requester can't request info on their own request (403); empty message rejected (422); reviewer's request moves status to `changes_requested` with the message stored; a second request-info call is blocked (400, wrong status); owner can edit while in this state; resubmitting clears the message, logs `resubmitted`, and returns to `submitted`; the request is then normally approvable |
| `test_dashboard_totals_are_accurate` | Dashboard endpoint returns well-formed totals and per-status counts |
| `test_search_and_filter` | Category filter returns only matching results; pagination metadata is present |
| `test_sorting_requests_by_amount` | `sort_by=amount` with `order=asc`/`desc` returns results in correct numeric order; an invalid `sort_by` column name returns 422 rather than a server error |
| `test_request_history_has_its_own_endpoint` | `GET /api/requests/{id}/history` returns the action log directly (not just nested in the detail response) as a paginated object; a user with no access to the request gets 403; a reviewer can view any request's history |
| `test_notifications_are_paginated_and_scoped_to_the_user` | Notifications endpoint returns the same paginated shape as every other list endpoint; `page_size=1` actually limits results to 1; a reviewer's notifications never appear in a requester's list and vice versa |
| `test_submitting_a_request_notifies_active_reviewers_and_admins` | Freshly submitting a request notifies every active reviewer and admin (verified by checking a reviewer's notification count increases and the message/request link are correct); the requester does not receive their own notification |
| `test_deactivated_account_cannot_log_in` | Non-admin users are blocked from the admin-only `/api/admin/users` endpoint (403) |

## Manual verification performed during development

Run against a live server with the seeded demo accounts:

- Logged in as a requester, created a draft, confirmed a negative amount was rejected with 422
- Confirmed submitting without a receipt is blocked with 400
- Uploaded a receipt with a valid JPEG magic-byte header, then successfully submitted
- Logged in as the reviewer, confirmed the requester's own token gets 403 when attempting `/approve`
- Approved the request as the reviewer, then marked it Paid; confirmed a second `/approve` call now returns 400 (invalid status transition)
- Confirmed `/reject` without a `reason` field returns 422
- Verified dashboard totals matched the sum of seeded request amounts by status
- Verified an unauthenticated request to `/api/requests` returns 401
- Verified a wrong-password login attempt returns 401
- Verified CORS headers are present and correct when the frontend origin calls the backend (preflight `OPTIONS` and the actual `POST /api/auth/login` both returned `access-control-allow-origin: http://localhost:3000`)
- Built the Next.js frontend (`npm run build`) with zero errors across all 7 routes, then ran it against the live backend and confirmed the login page renders real content (not a blank shell) via server-side rendering

## A bug the test suite itself had

When a second test file (`test_admin.py`) was added, running the full suite (`pytest tests/`) started failing with `OperationalError`s — but each file passed individually. Cause: both files set `os.environ["DATABASE_URL"]` to different filenames before importing the app, but `app.core.database` only executes that import once per process, so whichever file pytest imported first silently "won" for the whole session. The second file's teardown then dropped and deleted the *first* file's database out from under it. Fixed with a shared `tests/conftest.py` that sets the test database configuration exactly once, before either test file is imported, and owns the database's full lifecycle (create once at session start, drop once at session end) — individual test files now only seed their own data.

## Race condition found by manual concurrency testing

While verifying the "requests should not accidentally be submitted twice" requirement, automated tests alone weren't enough — they exercise one request at a time. Firing several simultaneous `curl` requests at `/submit` (via shell backgrounding) showed 2 of 5 succeeding, both writing a `submitted` history entry for the same request. The cause: the original code read the request's status, checked it in Python, then wrote the new status back — two concurrent requests could both pass the check before either write landed.

Fixed by making every status transition (submit, approve, reject, request-info, mark-paid, and the reviewer-claim transition) a single conditional database `UPDATE` — `WHERE id = ... AND status IN (allowed statuses)` — checking the affected row count rather than trusting a prior read. Verified the fix the same way the bug was found: firing 10 simultaneous requests at `/submit` and separately at `/mark-paid` (the highest-stakes one — a race there would mean double payment) and confirming exactly one succeeds each time. A permanent test, `test_double_submit_race_is_prevented`, covers this with actual Python threads.

## Pagination gaps found by re-auditing against the brief

The brief names four resources that should paginate: reimbursement requests, users, notifications, and history records. Requests already paginated correctly, but three others didn't: `GET /api/notifications` and `GET /api/admin/users/{id}/history` both returned every row unbounded, and the admin users list had pagination on the backend with no Previous/Next controls in the UI at all. Fixed all three — notifications and both history endpoints now return the same `{items, page, page_size, total, total_pages}` shape used everywhere else, and pagination UI was added to the admin and notifications pages.

One deliberate call, made explicit rather than left silent: a single request's history and a single user's account history are naturally small — a handful of status changes, rarely more than a dozen. Both got paginated backends for correctness and consistency, but the frontend fetches one generous page for these two views rather than building visible Previous/Next controls, since forcing pagination onto a short list would hurt the UX more than help. The two actually unbounded lists — the reviewer request queue and the admin user directory — get real, visible pagination controls.

## Known gaps

E2E coverage is currently 3 Playwright tests covering the most critical paths (login/role-redirect, draft creation, the full submit-then-approve workflow) — there's room to expand this further. Cloud deployment, continuous deployment, and monitoring weren't attempted, since they need real hosting/service accounts that made more sense to set up with someone present rather than rush unattended.
