[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/a4ah7HrK)
# CDF SDE Hackathon

**Build a Simple Expense & Reimbursement Tracker**

**Live URL:** <!-- Add your deployment URL here before submission e.g. https://your-app.vercel.app -->

Welcome! This is your personal repository for the CDF SDE Hackathon, a full-stack software development challenge.

Your goal is to build a simple, secure, and user-friendly application where users can submit and track reimbursement requests while authorized reviewers approve, reject, and manage those requests through completion.

The full problem statement is included in this repository. Read it carefully before you begin.

---

## 📋 Problem Statement

See [`problem_statement.md`](./problem_statement.md) for the full hackathon brief.

The application should replace an unstructured email- or spreadsheet-based reimbursement process with one clear workflow that answers:

1. What reimbursement requests have been submitted?
2. What is the current status of each request?
3. What action must the requester or reviewer take next?

Use only fictional or synthetic information when building and demonstrating your solution.

---

## 🎯 Level

This is a **5-day individual full-stack software development challenge**.

Focus first on building a reliable end-to-end reimbursement workflow:

**Create → Submit → Review → Approve / Reject → Paid**

The core requirements are intentionally achievable within the hackathon period. Optional enhancements are available for participants who complete the core workflow early.

A smaller, dependable application with strong engineering fundamentals will score higher than a feature-heavy application with an incomplete core workflow.

How you design and build it is up to you.

---

## 🗂️ Repo Structure

```text
├── README.md               # This file - live URL and submission checklist
├── problem_statement.md    # Full hackathon brief
├── planning/
│   └── planning.md         # Your planning document (fill this out first)
├── src/                    # Your application code goes here
└── docs/
    ├── walkthrough.md      # Link to your 3-5 minute walkthrough video
    ├── architecture.md     # Application architecture and data-flow explanation
    ├── testing.md          # Test cases and evidence of testing
    └── reflection.md       # What you built, tradeoffs, AI tools/resources used
```

---

## 🚀 Getting Started

1. **Read the problem statement** - [`problem_statement.md`](./problem_statement.md)
2. **Fill out your planning document** - [`planning/planning.md`](./planning/planning.md) before writing code
3. **Design your workflow** - define your users, data model, request statuses, APIs, and core application flow
4. **Build your solution** inside the `src/` directory
5. **Implement the core workflow first** - create, submit, review, approve/reject, and mark requests as Paid
6. **Test your application** - include validation, role permissions, workflow transitions, and error cases
7. **Deploy your application** using an appropriate hosting service and keep secrets in environment variables, never in the repository
8. **Update this README** with your live URL and submission information before the deadline

---

## ✅ Core Requirements

Your application should demonstrate a connected end-to-end reimbursement workflow.

### Requester

A requester should be able to:

* Create a reimbursement request
* Enter the expense title, amount, date, category, and description
* Attach or reference a receipt
* Submit the request for review
* View current and previous requests
* Track request status
* View reviewer comments or rejection reasons

### Reviewer

A reviewer should be able to:

* View submitted requests
* Review expense details and receipts
* Approve or reject requests
* Provide a reason when rejecting a request
* Mark an approved request as **Paid**
* Search and filter requests
* View basic financial summaries

### Recommended Request Statuses

* Draft
* Submitted
* Under Review
* Approved
* Rejected
* Paid

You may combine **Submitted** and **Under Review** if your workflow is clearly explained.

---

## 🔐 Engineering Expectations

Your solution should demonstrate the fundamentals of building a reliable full-stack application.

This includes:

* Frontend development
* Backend development
* Persistent database storage
* CRUD operations
* User roles and permissions
* Workflow and status management
* Form validation
* Error handling
* Basic application security
* Search and filtering
* Testing
* Documentation

Your implementation should also demonstrate appropriate access control. Requesters must not be able to approve or reimburse their own requests, and protected actions should be enforced by the backend.

Store secrets, API keys, and database credentials using environment variables and never commit them to the repository.

---

## 📊 Dashboard

Your application should provide a basic dashboard showing at least:

* Total amount requested
* Total amount approved
* Total amount pending
* Total amount paid
* Number of requests by status

Reviewers should be able to quickly understand what requires their attention.

---

## 📦 Submission Checklist

Push your completed work to your designated repository before the **5-day deadline**. Your repository state at the deadline is your submission.

* [ ] Live deployment URL added at the top of this README
* [ ] Completed planning document in `planning/planning.md`
* [ ] Working full-stack application in `src/`
* [ ] Requester and reviewer workflows implemented
* [ ] Create and submit reimbursement requests
* [ ] Approve and reject requests
* [ ] Rejection reason displayed to the requester
* [ ] Approved requests can be marked as Paid
* [ ] Request status and history can be viewed
* [ ] Search and filtering implemented
* [ ] Dashboard totals implemented
* [ ] Persistent data storage implemented
* [ ] Input validation and error handling implemented
* [ ] Role-based permissions enforced
* [ ] Receipt handling or receipt references implemented
* [ ] Test cases or evidence of testing included
* [ ] Sample fictional data included
* [ ] `docs/walkthrough.md` - walkthrough video link filled in
* [ ] `docs/architecture.md` - architecture and data flow documented
* [ ] `docs/testing.md` - testing approach and important test cases documented
* [ ] `docs/reflection.md` - implementation decisions, tradeoffs, and tools/resources disclosed
* [ ] README contains setup and run instructions
* [ ] Demonstration credentials provided, if authentication is required
* [ ] Known limitations and future improvements documented
* [ ] Clean commit history

---

## 🧪 Minimum Demonstration Scenario

Your walkthrough should demonstrate the full application workflow.

Show the following:

1. Create a new reimbursement request
2. Trigger and explain at least one validation error
3. Submit a valid request
4. View the request as a reviewer
5. Approve one request
6. Reject another request and provide a reason
7. Mark an approved request as **Paid**
8. Filter or search the requests
9. Show the dashboard totals
10. Explain how the application stores and protects its data

This common flow helps judges compare submissions consistently.

---

## 🎥 Video Requirements

Your **3-5 minute walkthrough video** is mandatory.

It should cover:

* What you built and why
* Your technology stack
* The requester workflow
* The reviewer workflow
* Creating and submitting a reimbursement request
* Validation and error handling
* Approving and rejecting requests
* Marking an approved request as Paid
* Search or filtering
* Dashboard totals
* How your data is stored
* How roles and permissions are enforced
* Important testing you performed
* Known limitations and what you would improve next

Link your video in `docs/walkthrough.md` before the deadline.

---

## 🏆 Evaluation

Submissions will be evaluated using the following rubric:

| Evaluation Category               |   Weight |
| --------------------------------- | -------: |
| Core functionality and workflow   |  **30%** |
| Code quality and organization     |  **15%** |
| User experience and accessibility |  **15%** |
| Validation and error handling     |  **10%** |
| Data design and persistence       |  **10%** |
| Security and role management      |  **10%** |
| Testing, documentation, and setup |  **10%** |
| **Total**                         | **100%** |

Judges will prioritize a working, reliable core workflow over unnecessary complexity or unfinished optional features.

---

## ✨ Optional Enhancements

Once the core requirements work correctly, you may add enhancements such as:

* Email or in-app notifications
* Expense approval history
* Audit trail
* Receipt image preview
* Receipt data extraction
* CSV or PDF export
* Monthly expense charts
* Budget-limit warnings
* Duplicate-request detection
* Editable drafts
* Resubmission after rejection
* Multiple approval levels
* Accessibility improvements
* Responsive mobile layouts
* Automated testing
* Dockerized setup
* Cloud deployment

Optional features should **complement, not replace, the core workflow**.

A solution with many unfinished features should not score higher than a simple and dependable solution.

---

## 🤖 AI Usage

AI tools may be used as development assistants where permitted by the announced CDF AI-use policy.

You are still responsible for:

* Understanding your architecture
* Understanding and explaining your code
* Making technical decisions
* Testing generated code
* Reviewing AI-generated changes
* Ensuring your solution satisfies the requirements

Disclose any AI tools, existing code, templates, tutorials, libraries, or external resources used in `docs/reflection.md`.

AI should assist your engineering process, not replace your understanding of the solution.

---

## 📝 A Note on Commit History

Your Git commit history is part of your submission and should clearly show how the application evolved.

A clean history looks like this:

* **Commit regularly** - at least once per meaningful chunk of work
* **Write descriptive messages** - avoid messages such as `fix`, `update`, or `asdf`
* **Do not squash everything into one commit** at the end
* **Do not commit API keys, `.env` files, credentials, uploaded receipts, or `node_modules`**
* Use `.gitignore` appropriately

Examples of useful commits:

```text
Add reimbursement request data model and API
Implement requester expense submission form
Add backend validation for reimbursement requests
Implement reviewer approval and rejection workflow
Add role-based access control
Add dashboard totals and request filters
Add receipt upload validation
Add reimbursement workflow tests
Add Docker setup and deployment configuration
```

Think of your commit history as a log of how you designed, built, tested, and improved your application, not just as a save button.

---

## ⚠️ Scope Reminder

You are **not** expected to build a complete financial or accounting platform.

You do not need to:

* Process real payments or reimbursements
* Connect to banks or credit cards
* Integrate with PayPal, Stripe, Razorpay, or other payment processors
* Perform tax or accounting compliance
* Build payroll functionality
* Use real organizational financial records
* Build complex multi-level approval chains
* Integrate with accounting platforms
* Build enterprise-level security infrastructure

Focus on delivering a clear, secure, tested, and understandable reimbursement-management workflow.

**Use fictional or synthetic data only.**
