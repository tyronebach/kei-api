# Codebase Audit Findings

Archived pre-hardening audit. Findings in this document describe the repository
state at the time of review and may have been fixed by later hardening commits.
Use active docs, tests, and current code as the source of truth for present
behavior.

## 1. Executive Summary

Overall health: this is a small, understandable FastAPI plus CLI repo, but it is not consistently enforcing its own highest-risk rule: scope isolation. The standard CRUD routers mostly follow the same scoped pattern. The outlier routers and ingestion edge cases do not.

Biggest risks:

- Critical scope leaks in `routers/snapshots.py` and `routers/audit.py`.
- Critical external-identity leak in `routers/transactions.py`: an existing `(external_source, external_id)` row is returned or restored without confirming it belongs to the requested scope.
- Silent broadening of summary queries when `period`, `source`, or category `type` are invalid.
- CLI code hides API failures in several places and frequently substitutes empty dicts, zeros, and defaults.
- Most tests use `Base.metadata.create_all()`, so most route tests do not exercise the Alembic schema.

Main sources of complexity:

- Router modules contain business logic, persistence, authorization, response shaping, duplicate detection, and integration-specific behavior in the same functions.
- CRUD/write/scope/update/delete logic is repeated across routers.
- The CLI repeats response parsing, ID-prefix resolution, and display fallbacks across command modules.
- Transaction ingestion has too many implicit modes: manual create, duplicate match, probable match, Tributary reconcile, Tributary enrichment, soft-deleted external row restore, and `force_create`.

What should be fixed first:

1. Fix scope enforcement in snapshots, audit, and external-identity transaction lookup.
2. Make invalid query params fail with 422 instead of silently returning broader data.
3. Remove CLI swallowed errors that turn API failures into fake empty states.
4. Add regression tests for the scope leaks and bad fallbacks before refactoring.
5. Preserve existing response shapes and auth entry points while system services depend on them; fix authorization and validation first, then coordinate any contract changes.

What should be deleted first:

- Root database backup `kei.db.bak-20260315-185844` if it is tracked or intentionally kept in the project root and is not part of the live operational DB. It is a runtime artifact, not source.
- Local/generated artifacts from source control if any are tracked: `__pycache__/`, `.pytest_cache/`, `data/`, `kei.db`, `*.db-wal`, `*.db-shm`. Do not delete live `data/` contents as cleanup.
- The malformed `.gitignore` pattern `IMP*.mdkei.db.bak*`, which should be split so backups are actually ignored.
- Misleading migration downgrade code after deciding the repo's downgrade policy. Do not squash or rewrite historical migrations in a running deployment without a deliberate migration reset plan.

Operational constraint: Kei is already serving system services. The safe path is not a broad hard cut. Apply narrow authorization, validation, and logging fixes that keep current public contracts stable. Treat response-shape changes, auth-mode removal, migration squashing, and endpoint deletion as coordinated compatibility work, not immediate cleanup.

## 2. Macro Architecture Issues

### Issue: Snapshot router bypasses scope authorization

Why it matters: snapshot data is scoped financial data. A scoped token can read any snapshot by ID or by `scope` parameter, and can write any valid scope because POST only checks write permission and `validate_scope()`. This directly violates "Scope enforcement is sacred."

Evidence / files involved:

- `routers/snapshots.py:13-30` lists snapshots and filters by requested scope without checking `agent.can_access_scope(scope)`.
- `routers/snapshots.py:34-47` returns latest snapshot for default `household` or any requested scope without access checks.
- `routers/snapshots.py:51-59` fetches by `snapshot_id` with no scope check.
- `routers/snapshots.py:63-83` POST validates the scope string and write permission, but not scope access.
- `docs/API.md:536` documents this as a current limitation.

Recommended direction: rewrite snapshot endpoints to use the same scope helpers as standard resources. Require `agent.can_access_scope(body.scope)` on POST. For read-by-ID, load the row and reject if the row scope is not allowed. Add tests for list/latest/get/post with a single-scope token.

Severity: Critical

### Issue: Audit router is unscoped and has a cross-scope destructive endpoint

Why it matters: audit counts expose global transaction information to any authenticated token, and `DELETE /api/audit/soft-deleted` deletes all soft-deleted transactions for any write-capable token regardless of allowed scopes.

Evidence / files involved:

- `routers/audit.py:16-47` counts all transactions without `apply_scope_filter()`.
- `routers/audit.py:51-67` deletes all soft-deleted transactions with no scope filter and no wildcard/admin-only check.

Recommended direction: first restrict purge to wildcard/admin principals or add explicit scoped deletion. Do not remove the endpoint blindly while services may rely on it. If audit stats are meant for scoped agents, add a required or optional `scope` and apply the normal scope helper.

Severity: Critical

### Issue: External identity lookup can leak or restore rows across scopes

Why it matters: `POST /api/transactions` validates access to the submitted scope, then looks up an existing external identity globally. If the same external identity exists in another scope, the API returns it or restores it without checking that existing row's scope. This is a direct data leak and possible cross-scope mutation.

Evidence / files involved:

- `routers/transactions.py:197-201` validates `body.scope`.
- `routers/transactions.py:207-220` queries `Transaction.external_source == body.external_source` and `Transaction.external_id == body.external_id` with no scope predicate, no `agent.can_access_scope(existing.scope)`, and no check that `existing.scope == body.scope`.

Recommended direction: include `Transaction.scope == body.scope` in the external identity lookup or fail loudly on cross-scope identity collision. Do not restore a soft-deleted external row unless its scope matches the requested scope and the agent can write that scope.

Severity: Critical

### Issue: Summary endpoints silently broaden invalid queries

Why it matters: invalid analytics inputs should be rejected. Returning a default month or unfiltered result makes financial data look valid while answering a different question.

Evidence / files involved:

- `routers/summary.py:22-49` returns the current month for any unknown `period`.
- `routers/summary.py:62-82` treats unknown `source` the same as `all` or omitted.
- `routers/summary.py:408-438` ignores invalid `type` values instead of returning 422.

Recommended direction: constrain `period`, `source`, and `type` with `Literal` or FastAPI `Query(pattern=...)`. Remove the fallback branch in `_resolve_period()`.

Severity: High

### Issue: Transaction ingestion is too implicit and integration-specific

Why it matters: one route owns external idempotency, soft-delete restore, duplicate detection, Tributary-specific reconciliation, manual enrichment inference, ORM writes, and response shape flags. That makes correctness hard to audit and invites more hidden modes.

Evidence / files involved:

- `routers/transactions.py:23-180` contains fuzzy scoring and reconciliation helpers.
- `routers/transactions.py:187-298` contains the full create path with multiple implicit outcomes.
- `schemas.py:113` exposes `force_create`, a bypass flag that skips duplicate/reconcile checks.

Recommended direction: keep one canonical create endpoint, but split the decision flow into explicit, tested steps with names that reflect product behavior. Do not add a generic framework. Start by extracting only the external-identity lookup and duplicate/reconcile decision into small pure functions that return explicit action results.

Severity: High

### Issue: Response contracts are inconsistent

Why it matters: the API normally returns `{"data": ..., "meta": ...}`. Snapshot and audit endpoints return raw objects/arrays. The CLI then compensates with broad `.get("data", result)` fallbacks, which hide response contract mistakes.

Evidence / files involved:

- `docs/API.md:44-60` explicitly lists exceptions.
- `routers/snapshots.py:12-83` uses raw `response_model` returns.
- `routers/audit.py:45-67` returns raw stats and raw delete count.
- CLI modules repeatedly use `result.get("data", result)` and `result.get("data", [])`.

Recommended direction: do not hard-cut existing snapshot/audit shapes while live consumers may rely on them. Freeze and document the current exceptions, add shape validation in the CLI, and only introduce envelope changes through a coordinated versioned change. Avoid adding more CLI-side guessing.

Severity: Medium

### Issue: Most route tests bypass migrations

Why it matters: model tests created with `Base.metadata.create_all()` can pass while production Alembic schema fails or lacks constraints. There is one migration parity test, but most behavior tests do not run against migrated schema.

Evidence / files involved:

- `tests/conftest.py:17-23` creates test tables with `Base.metadata.create_all()`.
- `tests/test_migrations.py:19-47` separately validates a few migration invariants.

Recommended direction: keep the fast `create_all()` fixture for simple unit-style router tests if needed, but add a migrated DB fixture for high-risk integration tests: scope enforcement, transactions, item movements, snapshots, and audit. Add tests for Alembic constraints that matter to runtime behavior.

Severity: Medium

### Issue: Weak runtime contracts for JSON-heavy fields

Why it matters: `meta`, snapshot `data`, token `allowed_scopes`, and token `permissions` are stored and returned as generic dict/list values. This is acceptable as an extension point, but it is currently trusted too broadly at boundaries.

Evidence / files involved:

- `schemas.py:55-353` uses `meta: dict | None` and snapshot `data: dict`.
- `db/models.py:30-178` uses unparameterized `Mapped[list]` and `Mapped[dict]`.
- `dependencies.py:57-63` trusts `allowed_scopes` and `permissions` from DB rows without runtime shape validation.

Recommended direction: do not create a meta schema system yet. Do add small boundary checks for security-critical JSON fields (`allowed_scopes`, `permissions`) and size/type limits for arbitrary snapshot/meta payloads.

Severity: Medium

### Issue: CLI mixes transport, domain fallback, rendering, and process exits

Why it matters: `KeiClient` exits the process instead of returning typed errors, command modules parse loose dicts, and high-level commands hide failures as empty states. This makes CLI behavior hard to test and easy to misread.

Evidence / files involved:

- `cli/kei/kei/client.py:37-67` prints and calls `sys.exit(1)` inside the HTTP client.
- `cli/kei/kei/client.py:105-126` swallows prefix-resolution exceptions and returns the original prefix.
- `cli/kei/kei/summary.py:365-404` catches `SystemExit` and renders partial "pulse" output as if missing data were normal.

Recommended direction: keep Typer commands responsible for exiting. Let client methods raise a clear custom exception or return explicit error results. Remove swallowed lookup failures.

Severity: Medium

### Issue: Repository hygiene is inconsistent

Why it matters: runtime DB artifacts and malformed ignore rules create risk of accidentally committing private data or backups.

Evidence / files involved:

- `.gitignore:17` contains `IMP*.mdkei.db.bak*`, a concatenated pattern.
- `rg --files` surfaced `kei.db.bak-20260315-185844`.
- `find` showed local `data/`, `kei.db`, `*.db-wal`, `*.db-shm`, `__pycache__/`, `.pytest_cache/`, `.venv/`, and `.venv312/`.

Recommended direction: fix `.gitignore`, confirm what is tracked, and remove any tracked runtime artifacts. Ignored local artifacts can stay local, but they should not appear in source listings.

Severity: Medium

## 3. Micro Refactoring Opportunities

### `routers/snapshots.py:13-83`

Problem: all snapshot routes bypass standard scope helpers.

Why it is bad: scoped financial snapshots are readable and writable outside token scope.

Recommended refactor: rewrite with `apply_scope_filter()` for lists, row-scope checks for get/latest, and explicit write-scope checks for POST.

Action: rewrite.

### `routers/audit.py:16-67`

Problem: audit stats and purge are global.

Why it is bad: a scoped writer can delete every soft-deleted transaction.

Recommended refactor: admin-gate the purge endpoint now unless a scoped purge contract is required. Only delete it after checking dependent services. Scope stats or require wildcard admin.

Action: rewrite or admin-gate.

### `routers/transactions.py:207-220`

Problem: external identity match ignores scope.

Why it is bad: returns/restores rows from a different scope.

Recommended refactor: include scope in the lookup or fail with a clear 409 on cross-scope external identity collision.

Action: rewrite.

### `routers/transactions.py:23-24`, `schemas.py:102`, `schemas.py:130`

Problem: dollar amounts are `float` and converted with `round(amount * 100)`.

Why it is bad: binary float and banker's rounding can misstate cents for edge inputs.

Recommended refactor: accept `Decimal` for dollar inputs or accept integer cents at the API boundary. Keep DB integer cents.

Action: simplify contract.

### `routers/transactions.py:323-326`

Problem: `from` and `to` date filters are raw strings.

Why it is bad: invalid dates become lexicographic SQL comparisons instead of validation errors.

Recommended refactor: validate with the existing `parse_date()` or a shared date query dependency before filtering.

Action: simplify.

### `routers/entities.py:212-249`

Problem: entity activity queries filter by `Transaction.entity_id` but not by `Transaction.scope == entity.scope`.

Why it is bad: current writes try to prevent cross-scope references, but historical bad data or direct DB writes can still contaminate activity.

Recommended refactor: add transaction scope filters matching the loaded entity scope.

Action: simplify.

### `routers/items.py:207-214`

Problem: stock movement accepts `transaction_id` without checking existence or same-scope relationship.

Why it is bad: an item movement can link to a transaction from another scope. The DB FK can validate existence, not ownership.

Recommended refactor: if `transaction_id` is provided, load it through a scoped transaction check and require `transaction.scope == item.scope`.

Action: simplify.

### `routers/summary.py:22-49`

Problem: `_resolve_period()` defaults unknown periods to current month.

Why it is bad: typoed analytics requests silently return unrelated results.

Recommended refactor: reject unknown `period` with 422.

Action: simplify.

### `routers/summary.py:62-82`

Problem: `_apply_source_filter()` treats unknown `source` as no filter.

Why it is bad: `source=bnak` returns all data, not an error.

Recommended refactor: use an enum/Literal for `bank`, `cash`, `agent`, and `all`.

Action: simplify.

### `routers/summary.py:436`

Problem: invalid category `type` is ignored.

Why it is bad: `type=expnese` returns both income and expense categories.

Recommended refactor: use `Literal["income", "expense"] | None`.

Action: simplify.

### `routers/summary.py:493`

Problem: `start_month` is computed and unused.

Why it is bad: it is confusing slop in a date-sensitive endpoint.

Recommended refactor: delete the unused line.

Action: delete.

### `main.py:70-78`

Problem: health check swallows all DB exceptions and returns only `{"status": "unhealthy"}`.

Why it is bad: operators lose the actual failure reason unless they have separate logs.

Recommended refactor: keep the public response generic, but log the exception with enough detail for operators.

Action: simplify.

### `dependencies.py:55-63`

Problem: `KEI_API_TOKEN` remains a wildcard admin fallback.

Why it is bad: it is broad access if treated as an accidental compatibility path. It is not inherently wrong if it is the deliberate canonical operator credential for the running system.

Recommended refactor: decide whether the admin token is canonical infrastructure auth. If yes, document it as canonical admin auth, rotate it properly, and stop calling it backward-compatible. If no, remove it only after every dependent service has scoped agent tokens.

Action: investigate, then document as canonical or replace after migration.

### `db/connection.py:8`

Problem: importing DB connection always creates `data/`.

Why it is bad: tests and tooling that use non-file database URLs still get local filesystem side effects.

Recommended refactor: create the directory only when the configured SQLite URL points at a relative file under `data/`, or move directory creation to startup/deploy scripts.

Action: simplify.

### `tests/conftest.py:17-23`

Problem: default DB fixture uses `Base.metadata.create_all()`.

Why it is bad: it masks migration/runtime drift for most behavior tests.

Recommended refactor: introduce a migrated fixture for high-risk tests and keep `create_all()` only for narrow unit-style tests.

Action: merge with migration fixture where risk matters.

### `alembic/versions/e1f2a3b4c5d6_payment_method_constraint.py:78-85`

Problem: downgrade uses an empty `batch_alter_table()` block.

Why it is bad: it claims to remove a check constraint but does not clearly do so. This is likely ineffective and misleading.

Recommended refactor: either implement the downgrade explicitly or state that downgrade is unsupported and fail loudly.

Action: rewrite.

### `alembic/versions/b3f1a2c4d5e6_recurring_rules.py`

Problem: removed recurring feature remains as a historical migration step.

Why it is bad: new databases create recurring tables only to drop them in a later migration. Downgrades can recreate removed product surface.

Recommended refactor: investigate whether a new squashed baseline is acceptable. If not, leave the upgrade chain but remove any product-facing references and make downgrade policy explicit.

Action: investigate only. Do not squash active deployment history as routine cleanup.

### `cli/kei/kei/client.py:105-126`

Problem: short-ID resolution catches every exception and returns the unresolved short ID.

Why it is bad: a list endpoint outage becomes a misleading GET/PUT/DELETE against a partial ID.

Recommended refactor: let the lookup failure abort with a clear error. Only return the original ID if it is already a full ID.

Action: simplify.

### `cli/kei/kei/summary.py:365-404`

Problem: `pulse` catches `SystemExit` from API calls and turns failures into "No snapshot data" or empty trends.

Why it is bad: auth failures, server errors, and connection failures look like legitimate empty data.

Recommended refactor: distinguish 404/no data from transport/auth/server failures. Fail the command for the latter.

Action: rewrite.

### `cli/kei/kei/snapshots.py:25-129`

Problem: snapshot rendering assumes many nested arbitrary fields and fills missing values with placeholders.

Why it is bad: malformed snapshot payloads look like a valid empty financial snapshot.

Recommended refactor: validate the expected snapshot shape before rendering. If required sections are absent, show a clear schema error.

Action: simplify.

### `cli/kei/kei/entities.py:146-257`, `cli/kei/kei/lists.py:99-185`, `cli/kei/kei/client.py:105-126`

Problem: ID-prefix resolution exists both in command modules and in `KeiClient`.

Why it is bad: the command-level paths fail loudly, while client-level resolution swallows exceptions and falls back.

Recommended refactor: keep one prefix-resolution path and make it fail loud.

Action: merge.

### `.gitignore:17`

Problem: `IMP*.mdkei.db.bak*` is malformed.

Why it is bad: `IMP*.md` and `kei.db.bak*` are not being ignored as intended.

Recommended refactor: split into separate lines.

Action: simplify.

## 4. Dead Code & Slop Removal

| File / route / function / component | Reason it appears unused or low-value | Recommended action | Confidence |
|---|---|---|---|
| `kei.db.bak-20260315-185844` | Runtime database backup appeared in `rg --files`; backups do not belong in source. | Delete if tracked; otherwise fix ignore rules. | High |
| `.gitignore:17` | Concatenated pattern `IMP*.mdkei.db.bak*` is almost certainly a typo. | Simplify | High |
| `routers/snapshots.py` raw response shape | One-off response contract forces client-side shape guessing, but may be consumed by running services. | Document/freeze current shape; consider versioned envelope later. | Medium |
| `routers/audit.py DELETE /soft-deleted` | Destructive global cleanup endpoint with unclear ownership. | Admin-gate now; delete later only if no operational dependency exists. | High |
| `routers/summary.py:493` | Unused `start_month` variable. | Delete | High |
| `alembic/versions/e1f2a3b4c5d6_payment_method_constraint.py` downgrade | Empty batch block does not communicate real behavior. | Rewrite or fail loudly. | High |
| `alembic/versions/b3f1a2c4d5e6_recurring_rules.py` | Removed feature is still created then dropped in migration history. | Leave active migration chain; investigate a future major baseline reset only. | Low |
| `scripts/backfill_snapshots.py` | Hard-coded local path and `test-token`; one-off importer. | Investigate. Move to docs/runbook or make configurable if still used. | Medium |
| `cli/kei/kei/summary.py pulse` fallback blocks | Swallows command failures and renders fake partial success. | Rewrite | High |
| Repeated CRUD blocks in routers | Same write check, scope validation, update loop, soft delete repeated across resources. | Merge carefully into small helpers only where behavior is identical. | Medium |
| Repeated CLI `.get("data", result)` parsing | Hides response-contract drift. | Simplify after API contracts are explicit and consumer impact is known. | Medium |
| Local `__pycache__/`, `.pytest_cache/`, `.venv/`, `.venv312/`, `data/` | Generated/runtime artifacts present in workspace. | Ensure untracked/ignored; do not delete live runtime data as audit cleanup. | High |

## 5. Bad Fallbacks and Silent Failures

### Silent failures

| File path | Current behavior | Why it is dangerous | Recommended behavior |
|---|---|---|---|
| `cli/kei/kei/client.py:124-126` | Catches all exceptions during prefix resolution and returns the original short ID. | Lookup failures become misleading API requests. | Fail with a clear lookup/connection error. |
| `cli/kei/kei/summary.py:387-404` | Catches `SystemExit` from API calls and substitutes empty pulse data. | Auth/server/network failures look like no data. | Only treat real 404/empty responses as empty; fail for transport/auth/server failures. |
| `main.py:75-76` | Health check catches all DB exceptions and returns generic unhealthy response. | Operators cannot see root cause from app logs unless exception is logged elsewhere. | Log exception details while keeping public response generic. |
| `cli/kei/kei/client.py:48-49` | Any JSON parsing issue falls back to `response.text`. | Acceptable for display, but it erases structured error expectations. | Keep fallback but include "non-JSON error response" in output. |

### Hidden errors

| File path | Current behavior | Why it is dangerous | Recommended behavior |
|---|---|---|---|
| `routers/summary.py:49` | Unknown period returns current month. | Typoed request produces valid-looking wrong analytics. | 422 invalid period. |
| `routers/summary.py:80` | Unknown source applies no filter. | Typoed source returns all data. | 422 invalid source. |
| `routers/summary.py:436` | Unknown category type is ignored. | `type=expnese` returns mixed results. | 422 invalid type. |
| `routers/transactions.py:323-326` | Raw date strings are compared in SQL. | Invalid dates silently change result sets. | Validate `from` and `to` before filtering. |
| `routers/snapshots.py:26-29` | Raw date strings are compared in SQL. | Invalid snapshot date filters silently misbehave. | Validate dates. |

### Bad fallback data

| File path | Current behavior | Why it is dangerous | Recommended behavior |
|---|---|---|---|
| `cli/kei/kei/snapshots.py:19-129` | Missing snapshot fields render as em dash, `?`, or zero-like values. | Malformed snapshots look like legitimate partial financial data. | Validate required snapshot sections before rendering. |
| `cli/kei/kei/summary.py:64-93` | Missing response fields display zero totals and empty sections. | API contract break can look like a real zero-dollar month. | Assert expected response shape before rendering. |
| `cli/kei/kei/transactions.py:113-128` | Probable-match create path builds a synthetic success display from input values. | If server response shape changes, CLI still reports success-looking output. | Render from returned transaction data only; fail if created response lacks data. |
| `routers/transactions.py:213-220` | Reusing a soft-deleted external identity silently restores it. | A create request can mutate historical deletion state without an explicit restore endpoint. | Require explicit restore intent or document this as canonical idempotency behavior and scope-check it. |

### Fake success states

| File path | Current behavior | Why it is dangerous | Recommended behavior |
|---|---|---|---|
| `cli/kei/kei/summary.py:407-440` | Pulse prints a report even when one or more API calls failed. | Users may trust an incomplete report. | Print partial data only with explicit per-section error statuses, or fail the command. |
| `cli/kei/kei/items.py:147` | "All items are stocked" is shown for an empty low-stock response. | This is valid if endpoint succeeded, but indistinguishable from scope misconfiguration if API shape is wrong. | Keep only after response shape validation. |

### Missing loading/error states

This repo is mostly API/CLI, not a frontend. The equivalent issue is missing explicit error states in the CLI. The CLI commonly treats empty `data` arrays as valid "not found" states without validating response shape first.

### Error handling that should fail loudly

| File path | Current behavior | Why it is dangerous | Recommended behavior |
|---|---|---|---|
| `cli/kei/kei/config.py:13-18` | Invalid YAML or unreadable config raises raw exceptions. | This is fail-loud, but not user-friendly. | Keep failure, but wrap with a clear "invalid config file" message. |
| `dependencies.py:55-63` | Falls back to wildcard admin token if token table lookup fails. | Broad access must be deliberate and operationally controlled. | Decide whether this is canonical admin auth. If yes, document and rotate it; if not, migrate dependents first. |
| `docker-compose.yml:11` | Defaults `KEI_API_TOKEN` to `test-token`. | Compose can start a write-capable admin token without deliberate provisioning. | Require env var for non-local deployments or make the default local-only explicit. |

## 6. Duplication Map

### UI duplication

Files involved:

- `cli/kei/kei/entities.py`
- `cli/kei/kei/items.py`
- `cli/kei/kei/services.py`
- `cli/kei/kei/transactions.py`
- `cli/kei/kei/lists.py`

What is duplicated: table rendering patterns, empty-state messages, `.get()` fallback field access, and success messages.

Recommended consolidation: do not build a big rendering framework. Add only tiny helpers for response shape validation and ID display once API contracts are explicit.

### Hook duplication

No frontend hooks are present.

### Utility duplication

Files involved:

- `cli/kei/kei/utils.py:7`
- `cli/kei/kei/client.py:105`
- Command-local "Resolve truncated ID" blocks in `entities.py`, `lists.py`, and `transactions.py`.

What is duplicated: ID-prefix resolution.

Recommended consolidation: keep one resolver, make it fail loud, and call it consistently.

### Type duplication

Files involved:

- `schemas.py`
- `db/models.py`
- `cli/kei/kei/*.py`

What is duplicated: resource shapes are defined in Pydantic models, SQLAlchemy models, docs, and implicit CLI dict access.

Recommended consolidation: do not add a shared client SDK yet. Add response-shape assertions in the CLI and keep the API schema authoritative.

### API/data-fetching duplication

Files involved:

- `cli/kei/kei/client.py`

What is duplicated: one method per HTTP action per resource, plus repeated `_add_scope` and `_handle_response` usage.

Recommended consolidation: keep explicit methods, but remove fallback behavior and let command modules handle user-facing errors.

### Error-handling duplication

Files involved:

- All routers
- `cli/kei/kei/client.py`
- CLI command modules

What is duplicated: write permission checks, scope validation, update loops, soft-delete responses, no-fields-to-update checks, and empty-state rendering.

Recommended consolidation: add small API helpers only for identical write/scope/delete patterns. Do not abstract transaction ingestion or summary aggregation behind generic CRUD helpers.

### Search duplication

Files involved:

- `routers/entities.py:63-88`
- `routers/items.py:61-86`
- `search.py`

What is duplicated: list all candidates, score in Python, sort, paginate, return search meta.

Recommended consolidation: a small `search_records()` helper could reduce duplicated code, but it should also make the full-table scan explicit. For now, more important is adding query limits or documenting that search is in-memory.

## 7. Recommended Action Plan

### Immediate Cleanup

Tasks that are safe and obvious:

1. Fix `.gitignore:17` into separate patterns.
2. Remove `routers/summary.py:493` unused `start_month`.
3. Delete any tracked runtime DB backup such as `kei.db.bak-20260315-185844` only after confirming it is not live operational data.
4. Admin-gate `DELETE /api/audit/soft-deleted`; delete it later only if no dependent service uses it.
5. Make `cli/kei/kei/client.py:124-126` fail loud instead of returning unresolved short IDs.
6. Add tests proving snapshots reject cross-scope read/write.
7. Add tests proving audit stats and purge cannot cross scopes.
8. Add tests proving transaction external identity cannot return/restore a row from another scope.

### Structural Refactors

Tasks that improve architecture:

1. Bring snapshots into the standard scoped resource pattern.
2. Decide whether audit is a scoped user API or an admin-only operational API, then simplify it accordingly.
3. Keep existing snapshot/audit response shapes stable for now. Document and validate them; introduce envelope changes only as coordinated versioned work.
4. Split transaction create decision-making into explicit pure functions with tested outcomes. Keep the endpoint; reduce hidden branches.
5. Consolidate identical CRUD write/scope/delete patterns after the scope bugs are fixed.
6. Consolidate CLI ID-prefix resolution into one fail-loud path.

### Reliability Improvements

Tasks that make failures explicit:

1. Validate all date query params for transactions and snapshots.
2. Reject invalid summary `period`, `source`, and category `type`.
3. Replace CLI fake empty states with response-shape validation and explicit errors.
4. Log DB exceptions in `/health`.
5. Validate security-critical JSON fields from `agent_tokens`.
6. Use Decimal or integer cents at the API boundary for transaction amounts.
7. Add migrated-DB tests for scope enforcement and constraints.

### Deferred / Investigate Later

Tasks that may be useful but need more context:

1. Whether the wildcard `KEI_API_TOKEN` fallback is canonical infrastructure auth. If it is required by running services, document and rotate it instead of removing it.
2. Whether recurring migrations should ever be squashed into a new baseline. For the current running system, leave history intact unless there is a deliberate reset.
3. Whether `scripts/backfill_snapshots.py` is still an active operational script or a one-off import helper.
4. Whether `meta` needs per-resource size/type limits beyond security-critical fields.
5. Whether search should remain in-memory or move to a more explicit indexed approach as data grows.

## 8. Final Recommendation

Delete first: tracked non-live DB backups and the malformed ignore rule. Lock down the global audit purge endpoint before considering deletion.

Refactor first: scope enforcement for snapshots, audit, and transaction external identity. These are correctness and privacy issues, not style issues.

Do not touch yet: broad router reorganizations, response-envelope hard cuts, auth fallback removal, migration squashing, a generic CRUD framework, a scope table, or a meta schema system. Those are larger choices and will add complexity or operational risk before the current explicit bugs are fixed.

Smallest safe path: fix the three scope leaks without changing public response shapes, make invalid analytics inputs return 422, remove the CLI swallowed prefix-resolution error, and add focused regression tests. After that, clean up duplicate CRUD patterns and response-contract drift without inventing new architecture.
