# Kei API Code Review

Date: 2026-03-12

Scope:
- Focused review of Kei as a scoped transaction ledger, agent-facing API, and the downstream system Tributary writes into.
- Verified locally with `.venv312/bin/python -m pytest tests/ -q` on 2026-03-12: 55 tests passed.
- Review emphasis: ledger correctness, scope isolation, migration integrity, recurring settlement, and Tributary-safe integration.

## Findings

### 1. The transaction API has no idempotency contract, so Tributary retries will create permanent duplicates
Severity: High

`POST /api/transactions` always inserts a new row with a new UUID. There is no first-class external identity key, no uniqueness constraint for upstream writers, and no lookup API keyed by source identity. For the Tributary pipeline, that means any retry after an ambiguous failure can create duplicate ledger entries.

References:
- `routers/transactions.py:18`
- `db/models.py:92`

Why this matters:
- Tributary currently needs the Kei write path to be safe under retries and partial failures.
- A ledger should have a canonical idempotent write mechanism for external ingestion.

### 2. Money is stored and aggregated as `float`, which is the wrong primitive for a ledger
Severity: High

Transactions, recurring rules, and services all use floating-point amounts. Summary endpoints then sum and round those floats. That is acceptable for a lightweight app demo, but not for a high-confidence ledger that is supposed to be the sink for bank-fed data.

References:
- `db/models.py:52`
- `db/models.py:105`
- `db/models.py:197`
- `schemas.py:96`
- `schemas.py:314`
- `routers/summary.py:69`

Why this matters:
- Repeated aggregation and cross-system comparisons become sensitive to float drift.
- Tributary already uses integer cents; Kei downgrades that precision model at the integration boundary.

### 3. Cross-scope reference integrity is not enforced for transactions and recurring rules
Severity: High

Transactions can reference any `entity_id` that exists, regardless of scope. Recurring rules can do the same. The database foreign key only guarantees existence, not same-scope ownership, and the write routes do not validate that the referenced entity belongs to the same scope as the transaction/rule. Once that bad data exists, entity activity queries will read it back without a transaction scope filter.

References:
- `routers/transactions.py:18`
- `routers/transactions.py:92`
- `routers/recurring.py:138`
- `routers/recurring.py:200`
- `routers/entities.py:208`
- `db/models.py:62`
- `db/models.py:109`

Why this matters:
- Scope isolation is one of the repo’s core guarantees.
- A single bad cross-scope link can contaminate summaries and entity profiles.

### 4. Recurring settlement/materialisation is race-prone and can double-create occurrences
Severity: High

`generate_instances()` and `settle_due()` compute an in-memory set of existing `rule_date` values and then insert missing transaction rows. There is no database uniqueness constraint on `(rule_id, rule_date)`, so concurrent calls or retried calls racing each other can create duplicate recurring transactions.

References:
- `routers/recurring.py:475`
- `routers/recurring.py:568`
- `db/models.py:117`

Why this matters:
- Scheduled jobs and agent retries are exactly where race-driven duplicates happen.
- Ledger correctness should not depend on “probably only one caller.”

### 5. Production migration state can diverge from the ORM and tests
Severity: High

The recurring migration adds `transactions.rule_id` and `transactions.rule_date`, but it does not create the foreign key that the ORM model declares. Tests will not catch that because they build schema with `Base.metadata.create_all()` instead of running Alembic migrations. That creates a real risk of “tests green, production schema different.”

References:
- `alembic/versions/b3f1a2c4d5e6_recurring_rules.py:55`
- `db/models.py:117`
- `tests/conftest.py:16`

Why this matters:
- Schema drift is one of the easiest ways to corrupt a small SQLite system quietly.
- The recurring feature is now integrity-sensitive enough that migration parity needs to be tested explicitly.

### 6. `GET /api/lists` merges lists with the same name across scopes
Severity: Medium

The list summary groups only by `ListItem.list`, not by `(scope, list)`. For wildcard or multi-scope agents, `shopping` in `home` and `shopping` in `salon` will be merged into one logical list in the response.

References:
- `routers/lists.py:26`

Why this matters:
- This violates the repo’s own “scope enforcement is sacred” principle at the presentation layer.
- It makes cross-scope data ambiguous even when the caller is allowed to see both scopes.

### 7. The repo does not define one canonical production scope set
Severity: Medium

The API default config and deploy docs still describe `["salon", "home"]`. The CLI README says the canonical scope set includes `synthhub`. Tributary currently uses `home`, `salon`, `woodwards`, and `synthhub`. The implementation is config-driven, but the repo-level defaults and docs disagree about what “valid” means.

References:
- `config.py:7`
- `README.md:72`
- `DEPLOY.md:19`
- `cli/kei/README.md:38`

Why this matters:
- This is exactly the kind of config drift that breaks the Tributary pipeline on a fresh deploy.
- A tandem system needs one documented canonical scope contract.

### 8. The test suite covers API behavior well, but not the ledger invariants that matter most for Tributary
Severity: Medium

The current tests cover CRUD, scope filtering, validation, auth, summaries, and recurring behavior. They do not cover external-write idempotency, cross-scope reference validation, concurrent recurring settlement, or Alembic-vs-ORM schema parity.

References:
- `tests/test_transactions.py:25`
- `tests/test_scope_enforcement.py:8`
- `tests/test_recurring.py:218`
- `tests/conftest.py:16`

Why this matters:
- The missing tests line up directly with the highest-risk integration failures.
- Current coverage makes the API feel more solid than the ledger guarantees actually are.

## Open Questions

1. Should Kei be the canonical long-lived ledger for imported bank transactions, or mainly an agent-facing operational store with transaction support?
2. Is the `KEI_API_TOKEN` wildcard admin fallback still required, or can the system move fully to per-agent tokens?
3. For external ingestion, is a dedicated transaction identity field acceptable, or must idempotency be expressed via indexed `meta` keys only?
4. What is the canonical scope set going forward: `home`, `salon`, `synthhub`, and `woodwards`, or something else?

## Tandem Recommendations

1. Add a first-class idempotent ingest path for transactions.
   Options:
   - dedicated `external_source` + `external_id` columns with a unique constraint
   - or a dedicated indexed generated column derived from `meta.source` / `meta.tributary_id`

2. Stop using float for ledger money.
   At minimum:
   - `transactions.amount`
   - `recurring_rules.amount`
   - summary computations

3. Enforce same-scope references on write.
   Validate that:
   - `transaction.entity_id` belongs to the same scope
   - `recurring_rule.entity_id` belongs to the same scope
   - any future relational references obey the same rule

4. Add a uniqueness guarantee for recurring instances.
   A unique constraint on `(rule_id, rule_date)` would make `generate` and `settle` robust under retries and concurrency.

5. Test real migrations, not just ORM metadata.
   Add at least one test that boots a temp DB through Alembic and verifies expected constraints/indexes.

6. Define one canonical scope contract across API, deploy docs, CLI docs, and Tributary.

## Overall Assessment

Kei API is structurally clean and more thoroughly tested than Tributary, but it is not yet a high-confidence financial ledger for external ingestion. The biggest gaps are idempotent transaction writes, float-based money handling, same-scope reference enforcement, and migration/test parity. Those are the areas to fix first if Kei is going to be the durable sink for Tributary.
