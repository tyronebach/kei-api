# Tributary + Kei API Tandem Hardening Plan

Date: 2026-03-12

Purpose:
- Turn the two review docs into one implementation plan across both repos.
- Prioritize the Tributary -> Kei transaction path first.
- Keep the system personal, local, low-maintenance, and high-confidence.

Inputs:
- Kei API review: `docs/code-review-2026-03-12.md`
- Tributary review: `~/Projects/tributary/docs/code-review-2026-03-12.md`

## Goals

1. No duplicate Kei transactions from Tributary retries, crashes, or reruns.
2. No export of pending or stale bank data.
3. One canonical scope contract across both repos.
4. Ledger-safe money handling end to end.
5. Strong operational gates so cron either does the safe thing or fails loudly.

## Non-Goals

- No generic event bus.
- No compatibility shims for multiple historical write paths.
- No human-heavy reconciliation workflow beyond the minimum needed review queue.
- No broad product expansion before the bank-feed pipeline is safe.

## Core Invariants

These should become explicit tests and validation gates.

1. A single real-world transaction maps to at most one exported Kei ledger row from Tributary.
2. A Tributary transaction is exported only when it is posted, reconciled, scoped, and not excluded.
3. Kei transaction writes are idempotent for external ingesters.
4. Scope names and allowed scope sets are identical across both repos.
5. All money amounts round-trip without float drift.

## Phase 0: Shared Contract

Do this first. The rest depends on it.

### 0A. Define the canonical scope set

Repo: both

Decide and document the real production scope set. Based on the current repos, the likely target is:
- `home`
- `salon`
- `woodwards`
- `synthhub`

Changes:
- Update Kei `KEI_VALID_SCOPES` defaults/docs/examples.
- Update Tributary docs and validations to match the same list.
- Update any CLI docs and token provisioning docs.

Exit criteria:
- One scope list appears in both repos and docs.
- Fresh deployment of Kei accepts every Tributary scope without local patching.

### 0B. Define the cross-system transaction identity contract

Repo: both

Pick one canonical external identity model for Tributary-originated transactions in Kei.

Recommended contract:
- `source = "tributary"`
- `source_id = <tributary canonical_transaction.id>`
- Optional: `source_version = <updated_at or content hash>`

Recommended storage shape in Kei:
- Prefer dedicated columns:
  - `external_source`
  - `external_id`
- Add unique constraint on `(external_source, external_id)`

Fallback if you want to keep the schema thinner:
- Keep identity in `meta`, but add a reliable indexed/generated lookup path.

Exit criteria:
- There is exactly one documented way to identify a Tributary-originated Kei transaction.
- Tributary and Kei code both use the same field names.

## Phase 1: Kei as a Safe Sink

Do Kei first so Tributary has a safe target to write to.

### 1A. Add idempotent transaction ingest support

Repo: `kei-api`

Changes:
- Add external identity support to transactions.
- Enforce uniqueness at the DB level.
- Add one canonical API behavior for external writes:
  - either create-or-return-existing
  - or create/update-by-external-identity

Recommended shape:
- Keep `POST /api/transactions` for normal agent use.
- Add a dedicated ingestion-safe path, for example:
  - `POST /api/transactions/import`
  - or extend `POST /api/transactions` with external identity semantics

Requirements:
- Retrying the same Tributary transaction must not create a second row.
- If the same source row is sent with changed content, behavior must be explicit:
  - reject conflict
  - or allow controlled update

Tests:
- same payload twice -> one row
- same external identity after process retry -> one row
- conflict behavior is deterministic and documented

### 1B. Move ledger money to integer cents

Repo: `kei-api`

Changes:
- Replace float ledger amounts with integer cents for:
  - `transactions`
  - `recurring_rules`
- Keep services as floats only if they are truly catalog prices and not ledger values.
  Better option: move services to cents too for consistency.
- Update summary logic to aggregate integers and format at response boundaries.
- Add Alembic migrations and response compatibility handling as one clean transition.

Requirements:
- Tributary cents are stored in Kei without float conversion.
- All sums and comparisons are integer-safe.

Tests:
- round-trip cents exactness
- summary totals exactness across mixed transaction sets

### 1C. Enforce same-scope reference integrity

Repo: `kei-api`

Changes:
- On transaction create/update, validate `entity_id` belongs to the same scope.
- On recurring rule create/update, validate `entity_id` belongs to the same scope.
- Audit any other relational write paths for the same rule.

Requirements:
- No cross-scope references can be created through the API.
- Reads cannot be contaminated by a bad scoped reference.

Tests:
- cross-scope entity link rejected with `422` or `403`
- valid same-scope link accepted

### 1D. Make recurring materialization concurrency-safe

Repo: `kei-api`

Changes:
- Add unique constraint on `(rule_id, rule_date)` for materialized recurring transactions.
- Make `generate` and `settle` safe under repeated or concurrent execution.

Requirements:
- Two callers racing the same rule cannot create duplicate occurrences.

Tests:
- double-generate remains idempotent
- DB constraint blocks duplicates even if application logic races

### 1E. Make tests exercise real migrations

Repo: `kei-api`

Changes:
- Add at least one test path that boots a temp DB through Alembic instead of only `Base.metadata.create_all()`.
- Verify expected constraints/indexes exist after migration.

Requirements:
- ORM model drift from production schema is caught in tests.

## Phase 2: Tributary Export Correctness

Once Kei is safe, harden Tributary to use it correctly.

### 2A. Treat Plaid pending transactions as non-exportable

Repo: `tributary`

Changes:
- Persist pending state from Plaid source events.
- Create canonicals with correct `posted_status`.
- Exclude pending canonicals from export.
- Decide whether pending rows should exist in canonical at all or stay source-only until posted.

Requirements:
- No pending card hold or pending ACH is exported to Kei.

Tests:
- added pending transaction is not exportable
- pending -> posted transition becomes exportable only after update

### 2B. Fully propagate Plaid `modified` events into canonical state

Repo: `tributary`

Changes:
- Recompute canonical data from the linked primary source event on modification.
- Propagate at least:
  - amount
  - merchant
  - description
  - category / transaction kind
  - booked date
  - currency
  - posted status
- Re-run transfer classification when relevant.

Requirements:
- Canonical rows never drift from their primary source truth.

Tests:
- pending -> posted correction updates canonical correctly
- amount or merchant correction updates canonical and export payload

### 2C. Replace destructive Plaid removal behavior with reversible state

Repo: `tributary`

Changes:
- Do not hard-delete canonicals just because a Plaid source disappears.
- Introduce explicit tombstone / removed / suppressed state for source events and affected canonicals.
- If already exported, preserve auditability and make cleanup explicit.

Requirements:
- Local history remains explainable after Plaid removals.
- Downstream Kei cleanup, if needed, is explicit and reviewable.

Tests:
- removed source event does not silently erase exported history

### 2D. Switch export to the Kei idempotent identity contract

Repo: `tributary`

Changes:
- Export using the shared external identity contract from Phase 0B.
- Before creating a Kei transaction, check/create against that identity, not just amount/date heuristics.
- Stop ignoring prior Tributary-created Kei rows during duplicate checks.
- Treat “already exists for this identity” as success, not as a duplicate heuristic.

Requirements:
- Export is safe under retry, rerun, and partial crash recovery.

Tests:
- crash-after-create simulation does not produce duplicate Kei rows on rerun
- already-exported-by-identity path is idempotent

## Phase 3: Cross-System Gates

After the write path is safe, add the gates that keep cron honest.

### 3A. Add hard export preconditions in Tributary

Repo: `tributary`

Recommended default blocking gates:
- `needs-review == 0`
- `household_scope = 'unassigned' == 0`
- `posted_status != 'posted'` rows are excluded
- unhealthy sync connection blocks export
- optional: block export until Plaid `historical_update_complete = 1` for new connections

Requirements:
- Cron export either sends a clean batch or exits non-zero with explicit reasons.

### 3B. Make health reporting trustworthy

Repo: `tributary`

Changes:
- Clear `last_error_code` on successful sync.
- Set `reauth_required` based on real Plaid error classes.
- Surface export-blocking state clearly in `status` and `validate`.

### 3C. Tighten Kei duplicate handling for non-Tributary writes

Repo: both

Changes:
- Keep a weaker heuristic duplicate review path only for legacy/manual reconciliation.
- Do not use amount/date/scope alone as the authoritative blocker for Tributary-originated exports.

## Phase 4: Test Matrix

These are the minimum confidence tests to add.

### Tributary

- pending Plaid transaction lifecycle
- Plaid modified correction propagation
- Plaid removed transaction handling after export
- idempotent export retry behavior
- transfer false positive / false negative cases
- CSV same-day duplicate preservation or explicit review path
- validation gate behavior before export

### Kei API

- idempotent external transaction ingest
- integer-cent storage and exact summaries
- same-scope reference enforcement
- recurring uniqueness under duplicate calls
- Alembic migration parity test

### Tandem integration

- one canonical Tributary row -> one Kei row under reruns
- same export repeated after simulated crash -> still one Kei row
- scope mismatch in config fails fast before runtime damage
- modified Tributary transaction updates the Kei-facing representation deterministically

## Phase 5: Rollout Order

Keep this order. Do not interleave randomly.

1. Freeze scope contract and external identity contract.
2. Harden Kei idempotent ingest and ledger storage.
3. Add Kei migration-parity and integrity tests.
4. Update Tributary pending/modified/removed lifecycle handling.
5. Switch Tributary export to the new Kei identity contract.
6. Add export gates and operational status hardening.
7. Run backfill/reconciliation checks on a DB copy before touching live data.

## Deployment and Backfill Strategy

### Kei first

- Back up Kei DB.
- Apply migrations.
- Validate:
  - transaction create/read still works
  - recurring still settles
  - summary totals still match known samples

### Tributary second

- Back up Tributary DB.
- Implement lifecycle fixes.
- Run:
  - `npm run typecheck`
  - `npm test`
  - targeted sync/export dry-run checks

### Live cutover

- Disable cron briefly.
- Deploy Kei.
- Deploy Tributary.
- Run `tributary export --dry-run`.
- If clean, run one real export.
- Re-enable cron only after the first clean cycle.

## Go / No-Go Checklist

- [ ] Both repos use the same documented scope set.
- [ ] Kei has idempotent transaction ingest for external writers.
- [ ] Kei stores ledger money as integer cents.
- [ ] Tributary never exports pending transactions.
- [ ] Tributary propagates Plaid modifications into canonical rows.
- [ ] Tributary does not destructively erase exported history on Plaid removals.
- [ ] Tributary export is idempotent against Kei identity, not just heuristics.
- [ ] Real migration-path tests exist in Kei.
- [ ] Core lifecycle tests exist in Tributary.
- [ ] Cron blocks on unresolved review/unassigned/unhealthy states.

## Recommended First Implementation Slice

If you want the smallest high-value slice first, do exactly this:

1. Kei: add external transaction identity + unique constraint + idempotent write behavior.
2. Tributary: export by that identity instead of heuristic duplicate detection.
3. Tributary: block export of pending transactions.
4. Tributary: update canonical rows fully on Plaid `modified`.

That slice gives the biggest reduction in duplicate and dirty-ledger risk without overbuilding the system.
