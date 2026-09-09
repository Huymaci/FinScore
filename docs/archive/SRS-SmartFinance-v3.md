# Software Requirements Specification
## Smart Personal Finance Management System (SmartFinance / SPFM)
### Version 3.0 — As-built baseline and current product roadmap

| Field | Value |
|---|---|
| Document version | 3.0 (supersedes 2.0) |
| Date | 24 August 2026 |
| Project type | Bachelor internship project |
| Prepared for | ICTLab / USTH |
| Supervisor | MSc. Huỳnh Vinh Nam |
| Stack | HTML5/CSS/vanilla JavaScript · Python 3.11+ / Flask · SQLAlchemy 2.x · MySQL 8.0.16+ (InnoDB) |
| Source baseline | Repository state on 24 August 2026 |

---

## 1. Introduction

### 1.1 Purpose

This document consolidates SRS v1 and the reduced-scope SRS v2, then updates them to match the current SmartFinance web application. It is the baseline for implementation, testing, demonstration and acceptance from v3 onward.

Unlike the earlier documents, v3 explicitly distinguishes functionality already present in the repository from functionality planned for the current roadmap. A requirement marked **Implemented** is supported by the current backend and, where stated, the web interface. A requirement marked **Partial** has only part of its required delivery surface. A requirement marked **Planned** is approved scope but is not represented as completed work.

### 1.2 Product goal

SmartFinance helps an adult user understand and control personal cash flow. The system records manual and imported transactions, organises them by account and category, plans monthly budgets, calculates Safe-to-Spend, detects overspending risk and presents accessible statistics. It deliberately avoids payment execution and direct access to bank credentials.

### 1.3 Scope of v3

The v3 baseline includes:

- secure registration, authentication and account lifecycle;
- personal money accounts with archive/restore and Safe-to-Spend inclusion control;
- transaction and custom-category management;
- previewed CSV/XLSX statement import with duplicate/error resolution;
- monthly budgets, Safe-to-Spend and threshold/burn-rate alerts;
- dashboard and statistical views;
- responsive bilingual web UI with theme preferences and live refresh;
- privacy-aware administration APIs;
- consent-based budget-status sharing as the remaining Should-priority product feature.

### 1.4 Definitions

| Term | Meaning |
|---|---|
| Account | A manually declared cash wallet or bank account. It is not a live bank connection. |
| Active account | An account available for new entries. An archived account remains in historical data but is excluded from normal entry selectors. |
| STS account | An account whose balance and transactions are included in Safe-to-Spend. Users may exclude money they do not consider spendable. |
| Category nature | `COMMITTED`, `SEMI_FIXED` or `DISCRETIONARY`. |
| Safe-to-Spend (STS) | Spendable-account balance up to the selected month end, less the unspent portions of committed and semi-fixed monthly budgets. |
| Burn-rate alert | A warning raised when projected month-end category spending exceeds the configured budget tolerance. |
| Import template | A seeded per-bank mapping used to interpret a CSV/XLSX statement. |
| Probable duplicate | An imported row close to an existing manual transaction by account, date and amount, requiring a user decision. |
| ShareGrant | A revocable, expiring consent record allowing one registered user to see another user's derived budget statuses. |
| Administrative blindness | The rule that administrators can manage accounts and operations but cannot inspect identified users' balances or transaction content. |

### 1.5 Actors

| Actor | Description |
|---|---|
| Guest | Unauthenticated visitor who may read the privacy notice, register or log in. |
| User | Authenticated adult owning one personal ledger and its financial data. |
| Admin | Seeded operator account. Manages users and operational configuration without access to financial content. |
| Nightly job | Scheduled process that recomputes alerts and performs maintenance tasks. |

### 1.6 Status legend

| Status | Meaning |
|---|---|
| Implemented | Present in the current source baseline and covered by an API, service or web workflow. |
| Partial | A usable subset exists, but a required UI, automation or verification item remains. |
| Planned | Approved for the current roadmap; not yet implemented. |

---

## 2. Product Overview

### 2.1 Architecture

SmartFinance is a layered monolith:

```text
Browser: HTML/CSS/vanilla JS, Chart.js, Fetch API
                         |
                         | same-origin HTTPS/JSON
                         v
Flask routes -> services -> repositories -> SQLAlchemy models
                         |
                         v
                  MySQL 8 / InnoDB
```

Flask also serves the frontend. Session authentication and CSRF protection apply to state-changing requests. Business rules belong in services; ownership filters belong in service/repository access paths.

### 2.2 Assumptions and dependencies

- All monetary values are integer Vietnamese Dong (VND); multi-currency conversion is not supported.
- Users are at least 18 years old and supply a date of birth during registration.
- Transactions originate from manual entry or user-uploaded statements.
- Uploaded files are at most 5 MB.
- Production uses MySQL 8.0.16+; SQLite in-memory is limited to isolated tests.
- Deployment is a single application instance for the internship scope.

### 2.3 Design constraints

| ID | Constraint |
|---|---|
| CON-01 | Backend remains Python/Flask with SQLAlchemy ORM and Alembic migrations. |
| CON-02 | Frontend remains framework-free HTML/CSS/JavaScript for this scope. |
| CON-03 | Production persistence uses MySQL 8 InnoDB and `utf8mb4`. |
| CON-04 | Monetary columns use signed `BIGINT`; floating-point money is prohibited. |
| CON-05 | Secrets and database credentials come from environment variables. |
| CON-06 | Full bank account numbers, passwords, OTPs and bank credentials are never accepted or stored. |

---

## 3. Use Cases and Delivery Status

| ID | Use case | Actor | Priority | Status |
|---|---|---|---|---|
| UC-01 | Register, log in and log out | Guest/User | Must | Implemented |
| UC-02 | Manage profile, password, export and deletion request | User | Must | Implemented |
| UC-03 | Manage money accounts and STS inclusion | User | Must | Implemented |
| UC-04 | Manage transactions and custom categories | User | Must | Implemented |
| UC-05 | Preview a bank statement import | User | Must | Implemented |
| UC-06 | Resolve import duplicates/errors and confirm | User | Must | Implemented |
| UC-07 | Plan monthly budgets and calculate STS | User | Must | Implemented |
| UC-08 | Receive and handle spending alerts | User/Job | Must | Implemented |
| UC-09 | View dashboard and spending statistics | User | Must | Implemented |
| UC-10 | Use bilingual, themed and responsive preferences | User | Must | Implemented |
| UC-11 | Administer users and operations | Admin | Must | Partial — API complete, web UI planned |
| UC-12 | Share and revoke derived budget status | User | Should | Planned |

---

## 4. Functional Requirements

### 4.1 Authentication and account lifecycle

| ID | Requirement | Status |
|---|---|---|
| FR-01 | A guest can view a privacy notice before registration. Consent is opt-in and is not preselected. | Implemented |
| FR-02 | A guest can register using a unique, valid email, full name, date of birth and policy-compliant password. Registration rejects users younger than 18. | Implemented |
| FR-03 | A guest can log in. Five consecutive failures for the same account lock it for 15 minutes. A successful login clears previous session state and starts a new authenticated session. | Implemented |
| FR-04 | A user can log out, clearing authentication and session data. | Implemented |
| FR-05 | A user can view and update full name and consent state. | Implemented |
| FR-06 | A user can change password only after confirming the current password. | Implemented |
| FR-07 | A user can export personal data as a ZIP containing machine-readable JSON and CSV data. | Implemented |
| FR-08 | A user can submit an account-deletion request. An admin can execute the request and purge the user's personal records. | Implemented |

### 4.2 Ledger and money accounts

| ID | Requirement | Status |
|---|---|---|
| FR-09 | Registration creates exactly one personal ledger for the user. | Implemented |
| FR-10 | A user can create and edit `CASH` and `BANK` accounts with name and integer opening balance. | Implemented |
| FR-11 | A bank account may store a bank code and exactly the last four digits only. | Implemented |
| FR-12 | A user can archive and restore an account. Archived accounts and their transactions remain available for history and reporting. | Implemented |
| FR-13 | Each account has an `include_in_safe_to_spend` flag. The user can exclude savings/reserve accounts from the STS balance without deleting or archiving them. | Implemented |
| FR-14 | Account responses and personal-data exports include archive and STS-inclusion state. | Implemented |

### 4.3 Transactions and categories

| ID | Requirement | Status |
|---|---|---|
| FR-15 | A user can create, view, edit and delete an owned transaction with date, positive amount, `IN`/`OUT` direction, account, category and description. | Implemented |
| FR-16 | A user can list transactions with server-side pagination and filters for date range, account, category and direction. Page size is capped at 100. | Implemented |
| FR-17 | Every transaction-scoped operation verifies ownership; another user's identifier returns no financial object. | Implemented |
| FR-18 | The system seeds a two-level category tree whose leaf categories carry a nature. | Implemented |
| FR-19 | A user can add or rename custom categories. Deleting a used custom category requires a valid replacement category. | Implemented |
| FR-20 | Imported transactions are classified by ordered active regex rules; unmatched rows use `Uncategorised`. Confirm-time category overrides take precedence. | Implemented |

### 4.4 Statement import

| ID | Requirement | Status |
|---|---|---|
| FR-21 | A user uploads a `.csv` or `.xlsx` file, selects an owned target account and an active seeded import template. | Implemented |
| FR-22 | Templates support either one signed amount column or separate debit and credit columns. At least three bank formats are seeded. | Implemented |
| FR-23 | Import starts in preview mode. It reports new, duplicate, probable-conflict and erroneous rows without creating transactions. | Implemented |
| FR-24 | The system computes a SHA-256 deduplication key from account, posting date, amount, reference and description. Re-importing an identical file creates no new transactions. | Implemented |
| FR-25 | Rows resembling manual transactions by account, date within one day and amount within one percent require a merge/skip or keep-both decision. | Implemented |
| FR-26 | A user may override the proposed category before confirmation. | Implemented |
| FR-27 | Parsing failures retain source row number and reason and are downloadable as CSV. | Implemented |
| FR-28 | Confirmation atomically commits all accepted valid rows. A batch cannot be confirmed by another user. | Implemented |

### 4.5 Budgets and Safe-to-Spend

| ID | Requirement | Status |
|---|---|---|
| FR-29 | A user can create or update one budget per category and calendar month. Budget amounts cannot be negative. | Implemented |
| FR-30 | A user can copy the previous month's missing budgets into a selected month without overwriting existing values. | Implemented |
| FR-31 | STS includes opening balances and transactions only from accounts marked for STS, using transactions posted before the selected month end. | Implemented |
| FR-32 | STS reserves the remaining amount of `COMMITTED` and `SEMI_FIXED` budgets: `balance − Σ max(0, budget − spent)`. Discretionary budgets are shown for control but are not reserved twice. | Implemented |
| FR-33 | Dashboard, budgets and transactions can be navigated by month, including previous and next month controls. | Implemented |

### 4.6 Alerts

| ID | Requirement | Status |
|---|---|---|
| FR-34 | The threshold detector raises a warning at 80% and a critical alert at 100% of a category budget. | Implemented |
| FR-35 | The burn-rate detector projects month-end spending using the median historical cumulative fraction over six months, falling back to elapsed calendar fraction when history is insufficient. It alerts above 105% of budget. | Implemented |
| FR-36 | Alerts contain kind, severity, explanation, suggested action, status, category and trigger time. | Implemented |
| FR-37 | Equivalent alerts use a deduplication key and a 72-hour cooldown. | Implemented |
| FR-38 | A user can view the alert inbox and mark an alert read or dismissed. | Implemented |
| FR-39 | Alert calculation runs after confirmed imports and through the nightly command. Deployment scheduling of that command must be configured by the operator. | Partial |

### 4.7 Dashboard and statistics

| ID | Requirement | Status |
|---|---|---|
| FR-40 | The dashboard shows selected-month income, expense, net, STS and per-category budget progress with colour and text state. | Implemented |
| FR-41 | The statistics page shows expense breakdown for selectable 1/3/6/12-month periods and a trailing 12-month trend. | Implemented |
| FR-42 | Statistical and dashboard values refresh after financial mutations and automatically every 60 seconds while the page is active. Returning to a visible tab triggers refresh. | Implemented |
| FR-43 | The dashboard displays live local date/time, time-appropriate greeting and selected-month label. | Implemented |

### 4.8 Web experience and preferences

| ID | Requirement | Status |
|---|---|---|
| FR-44 | The web interface supports Vietnamese and English. The preference is saved locally and applies to static labels and recognised system-generated category, template and alert text. User-authored content is never translated. | Implemented |
| FR-45 | The user can choose light, dark or system-following theme. The selection is persisted locally and reacts to operating-system theme changes in system mode. | Implemented |
| FR-46 | Account management, language and theme preferences are consolidated under the profile control. Alerts have one canonical navigation entry. | Implemented |
| FR-47 | The interface is responsive, provides empty/loading/error states and formats VND and dates according to the selected language. | Implemented |
| FR-48 | Browser hash navigation and history preserve the selected main view. | Implemented |

### 4.9 Administration

| ID | Requirement | Status |
|---|---|---|
| FR-49 | Only a seeded `ADMIN` role can access administration endpoints; no registration or runtime elevation path creates an admin. | Implemented |
| FR-50 | Admin can search paginated user metadata, lock/unlock users, issue a temporary reset password and execute deletion. | Implemented |
| FR-51 | Admin can list seeded import templates/classification rules and toggle active state. Template/rule authoring remains a seed-script operation. | Implemented |
| FR-52 | Admin can view operational aggregates and paginated audit events. Aggregates derived from fewer than five users are suppressed. | Implemented |
| FR-53 | Admin responses never expose an identified user's accounts, balances, transaction amounts, merchants or descriptions. | Implemented |
| FR-54 | A responsive admin web screen shall expose FR-50 to FR-52 using the existing APIs and the same accessibility/security rules as the user UI. | Planned |

### 4.10 Consent-based sharing

| ID | Requirement | Status |
|---|---|---|
| FR-55 | A grantor can create a ShareGrant for a registered user by email with expiry no more than 90 days away. Only the data owner can initiate a grant; no access-request workflow exists. | Planned |
| FR-56 | The grantee sees read-only green/amber/red budget status by permitted category, calculated at request time. No amount, balance, transaction, merchant or description is serialised. | Planned |
| FR-57 | The grantor can revoke a grant immediately. Expired grants are invalid and never renew automatically. | Planned |
| FR-58 | Every successful grantee read creates an access record visible to the grantor, identifying viewer, scope and time. | Planned |
| FR-59 | All cross-user reads pass through one ShareAccessGuard and are covered by negative authorisation tests. | Planned |

---

## 5. Data Requirements

### 5.1 Current entities

`users`, `ledgers`, `accounts`, `categories`, `transactions`, `import_templates`, `import_batches`, `import_errors`, `categorization_rules`, `budgets`, `alerts`, `audit_logs`.

Planned sharing adds `share_grants` and `share_access_logs` only; friendship and household-ledger tables remain excluded.

### 5.2 Mandatory rules

| ID | Rule |
|---|---|
| DR-01 | Money is signed `BIGINT` VND. Transaction amounts are positive; direction carries the sign semantics. |
| DR-02 | Transaction deduplication uses a database-unique `BINARY(32)` SHA-256 digest. |
| DR-03 | Instants use MySQL `DATETIME(6)` in UTC and are converted for presentation. |
| DR-04 | User-owned data uses cascading foreign keys where deletion must erase personal data. |
| DR-05 | Account `include_in_safe_to_spend` is non-null and defaults to true. |
| DR-06 | Schema changes are applied through one-purpose Alembic revisions; production code does not call `create_all()`. |
| DR-07 | Tables use InnoDB, `utf8mb4` and `utf8mb4_0900_ai_ci`. |
| DR-08 | Enumerated domain values are constrained strings rather than native MySQL `ENUM`. |
| DR-09 | Required hot-path indices include account/date transactions, unique dedup key and user/trigger-time alerts. |
| DR-10 | Personal-data exports include all user-owned financial data and account STS preferences. |

---

## 6. External Interface Requirements

### 6.1 Web interface

- The application shall remain usable from 360 px mobile width through desktop layouts.
- Destructive actions shall state the affected object and request explicit confirmation.
- Colour shall not be the sole indicator of budget or alert state.
- User-visible errors shall explain the problem without exposing a stack trace.
- Forms shall provide labels, keyboard operation and visible focus state.
- Monetary values shall use locale-aware grouping and the `₫` suffix.

### 6.2 HTTP interface

The current same-origin endpoints are grouped under `/auth`, `/profile`, `/accounts`, `/categories`, `/transactions`, `/imports`, `/budgets`, `/alerts`, `/statistics` and `/admin`. v3 documents these as the compatibility baseline; migration to `/api/v1` is not required during the internship.

- Requests and responses use JSON except multipart uploads and downloadable ZIP/CSV files.
- State-changing requests require a valid CSRF token.
- List endpoints use `page` and `per_page` where pagination is required, with a maximum of 100.
- Normal outcomes use standard HTTP statuses including `200`, `201`, `202`, `400`, `401`, `403`, `404`, `409`, `413`, `422` and `429` as applicable.
- Error responses shall converge on one documented envelope in a future compatibility release; current clients must accept the existing `error` string response.

---

## 7. Non-Functional Requirements

### 7.1 Security and privacy

| ID | Requirement | Verification |
|---|---|---|
| NFR-01 | Passwords use Werkzeug PBKDF2-SHA256 with at least 600,000 iterations; plaintext and reversible passwords are prohibited. | Inspect hashes and auth tests |
| NFR-02 | Passwords contain at least 10 characters and three of four character classes, and reject common passwords. | Unit tests |
| NFR-03 | Session cookies are `HttpOnly`, `SameSite=Lax`, `Secure` under HTTPS, and expire after 30 idle minutes. Login clears prior session state. | Header/session test |
| NFR-04 | Login and registration are limited to 10 requests per minute. Upload and global production limits shall be configured before public deployment. | Rate-limit tests/config review |
| NFR-05 | CSRF applies to every state-changing browser request. | Negative request test |
| NFR-06 | ORM/bound parameters are mandatory; interpolated SQL is prohibited. | Static/code review |
| NFR-07 | Every object operation enforces owner or admin scope and prevents IDOR. | Cross-user tests |
| NFR-08 | Uploads enforce allowed formats, 5 MB maximum, safe temporary handling and scheduled cleanup. | Malicious-file/retention test |
| NFR-09 | Security headers include CSP, `nosniff`, frame denial and appropriate referrer/HSTS policy in production. | Header inspection |
| NFR-10 | Logs omit passwords, tokens, financial content and full email addresses. | Log review |
| NFR-11 | Account deletion removes all linked personal data. Only a non-reversible deletion proof may be retained. | Before/after database test |
| NFR-12 | Administrative blindness is enforced by absent query/serialization paths, not UI hiding. | Code review and attempted access |
| NFR-13 | The product performs no advertising, credit scoring, payment execution, model training on personal data or third-party disclosure. | Scope/code review |

### 7.2 Reliability, performance and quality

| ID | Requirement | Verification |
|---|---|---|
| NFR-14 | Import confirmation and each financial write are atomic. | Failure-injection tests |
| NFR-15 | Re-importing the same statement creates zero additional transactions. | Automated test |
| NFR-16 | Derived account balance equals opening balance plus IN minus OUT for the applicable transaction window. | Consistency test |
| NFR-17 | P95 read response is below 800 ms with 20,000 seeded transactions and 10 concurrent users. | Load-test report |
| NFR-18 | Dashboard rendering performs at most 10 SQL queries and avoids N+1 access. | Query-count assertion |
| NFR-19 | Overall automated coverage is at least 60%; import, dedup, budget and alert core logic each reach at least 85%. | Coverage report |
| NFR-20 | Unhandled errors return a generic response with correlation information; debug mode and Werkzeug debugger are disabled outside local development. | Error/deployment test |
| NFR-21 | Dependencies are pinned and have no known High/Critical vulnerability at release. | `pip-audit` report |
| NFR-22 | `ruff` and the automated test suite pass before a v3 release is tagged. | CI output |

### 7.3 Usability and accessibility

| ID | Requirement | Verification |
|---|---|---|
| NFR-23 | Primary user workflows function with keyboard input and have visible focus. | Manual accessibility check |
| NFR-24 | Vietnamese is the default language; English is user-selectable and no user-authored content is mutated by translation. | UI tests |
| NFR-25 | Light, dark and system modes retain readable contrast and do not flash an incorrect saved theme during startup. | Visual/manual test |
| NFR-26 | Live refresh does not overlap requests, and pauses while the document is hidden. | Frontend test |
| NFR-27 | A clean-machine setup using README and seed scripts completes in under 15 minutes, excluding image download time. | Installation rehearsal |

---

## 8. Acceptance and Traceability

### 8.1 Release acceptance

A v3 release is accepted when:

1. All **Implemented** requirements retain passing automated or documented manual evidence.
2. MySQL migration `20260822_03` is applied and existing accounts receive a valid STS-inclusion value.
3. The user can complete register → account → transaction/import → budget → alert/statistics workflows through the browser.
4. Excluding an account from STS changes STS but does not remove its transactions from ordinary history/statistics.
5. VI/EN and light/dark/system preferences survive reload; live dashboard refresh and month navigation work.
6. Admin API tests demonstrate role enforcement and administrative blindness.
7. Planned sharing requirements are not described as delivered until models, migration, guard, API, UI and tests all exist.

### 8.2 Required experiments retained from v2

- **E1 — Alert quality and lead time:** compare 80% threshold, linear pace and historical pace over at least 50 labelled synthetic overspending episodes; report precision, recall, F1 and mean days of warning before month end.
- **E2 — Duplicate detection:** report precision and recall for identical re-import, overlapping statement periods, import after manual entry and reordered rows.
- **E3 — STS account-selection correctness (new in v3):** verify STS across included/excluded accounts, archived accounts, prior/future transactions and committed/semi-fixed budget reserves.

### 8.3 Roadmap completion order

| Order | Work item | Exit condition |
|---|---|---|
| 1 | Harden current v3 baseline | Tests, migration, performance and security evidence pass |
| 2 | Admin web interface | FR-54 complete without exposing financial content |
| 3 | Consent-based sharing | FR-55–FR-59 complete with access-guard and audit tests |
| 4 | Experiments and final report | E1–E3 results and evidence included |

---

## 9. Excluded Scope and Rationale

| Excluded | Rationale |
|---|---|
| Direct bank/Open Banking integration | Requires bank/third-party contracts and a substantially different security and compliance boundary. File import remains the supported adapter. |
| Payment execution and bank credentials | SmartFinance is an analysis tool, not a payment service. |
| SMS/notification scraping | Platform restrictions and incomplete reference data make reliable reconciliation unsafe. |
| Friend requests and social network | ShareGrant already represents explicit, revocable consent; a separate relationship state machine adds no financial capability. |
| Household/shared ledger | Multi-owner tenancy materially expands every authorisation path and test. |
| Transaction-level or balance sharing | Merchant, description and balance data creates disproportionate privacy risk. |
| Access requests | Grantor-only initiation avoids pressure to disclose sensitive financial data. |
| Minors and parental control | Children's-data safeguards exceed this project's scope. Registration remains adult-only. |
| Recurring-payment prediction | Useful but not required to prove the current alert contribution. |
| Visual import-template authoring | Templates and rules remain controlled seed/configuration data. |
| Import rollback and soft-delete recovery | Convenience work deferred behind security, correctness and sharing. |
| Multi-currency, investment portfolios, debt products, mobile native apps and microservices | Outside the internship's product and architecture boundary. |

---

## Appendix A — Changes from v2

- Records the repository as an explicit as-built baseline instead of treating every requirement as equally delivered.
- Adds account archive/restore and per-account Safe-to-Spend inclusion.
- Corrects STS semantics to use a selected month-end transaction cutoff and spendable accounts only.
- Adds the delivered bilingual UI, light/dark/system themes, profile preference menu, responsive navigation, live clock/greeting and 60-second refresh.
- Documents dashboard month navigation and selectable statistics periods.
- Separates the implemented admin API from the still-planned admin web screen.
- Keeps consent-based L1 budget-status sharing as Planned and removes any implication that it already exists.
- Documents current same-origin endpoint paths instead of requiring an unimplemented `/api/v1` migration.
- Adds migration, preference and STS-account acceptance criteria plus experiment E3.

---

*SmartFinance SRS v3.0 — source-aligned baseline, 24 August 2026.*
