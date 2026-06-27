# Kei API Architecture

Status: current repo implementation.

## Overview

Kei API is a small FastAPI service for LLM-facing data operations. It stores scoped records in SQLite, exposes CRUD and aggregate endpoints, and keeps domain-specific details in JSON fields instead of adding domain columns.

## Stack

| Layer | Current implementation |
|---|---|
| App | FastAPI, sync route handlers |
| ORM | SQLAlchemy 2.x |
| DB | SQLite under `data/kei.db` by default |
| Migrations | Alembic, run outside app startup |
| Validation | Pydantic 2, strict input models |
| Search | `rapidfuzz` plus local Soundex helpers |
| CLI | Typer package in `cli/kei/` |

## Route Modules

| Router | Prefix | Responsibility |
|---|---|---|
| `routers/entities.py` | `/api/entities` | Named contacts, clients, vendors, places |
| `routers/transactions.py` | `/api/transactions` | Income/expense ledger rows, duplicate detection, external identity |
| `routers/items.py` | `/api/items` | Inventory, low-stock checks, movement logs |
| `routers/services.py` | `/api/services` | Service catalog |
| `routers/lists.py` | `/api/lists` | Lightweight named checklist/list items |
| `routers/snapshots.py` | `/api/snapshots` | Financial snapshot blobs keyed by `(scope, date)` |
| `routers/summary.py` | `/api/summary` | Pre-computed financial aggregates |
| `routers/audit.py` | `/api/audit` | Transaction audit counts and soft-delete purge |

## Data Model

Core tables:

- `entities`
- `transactions`
- `items`
- `item_movements`
- `services`
- `list_items`
- `snapshots`
- `agent_tokens`

Shared rules:

- IDs are UUID hex strings.
- Timestamps are Unix epoch integers.
- Standard operational resources use `deleted_at` soft delete.
- `transactions.amount` is stored as integer cents and exposed as dollar floats.
- `meta` is the extension point for resource-specific or importer-specific data.
- `created_by` and `updated_by` track the agent ID on standard scoped resources.

Foreign keys:

- `transactions.entity_id -> entities.id` with `ON DELETE SET NULL`
- `item_movements.item_id -> items.id` with `ON DELETE CASCADE`
- `item_movements.transaction_id -> transactions.id` with `ON DELETE SET NULL`

## Auth Model

Requests authenticate to an `AgentPrincipal`:

- `agent_id`
- `allowed_scopes`
- `permissions`

Token resolution:

1. Hash bearer token with SHA-256.
2. Match `agent_tokens.token_hash`.
3. If there is no row match, compare against `KEI_API_TOKEN`.
4. `KEI_API_TOKEN` becomes an admin principal with `allowed_scopes=["*"]` and `permissions=["read","write"]`.

Write endpoints require `write`. Standard scoped reads call `apply_scope_filter()`: if a non-wildcard agent omits `scope`, queries are constrained to that agent's allowed scopes.

Snapshot endpoints enforce `allowed_scopes` on reads and writes. Omitted-scope list reads follow the standard scoped-resource rule: wildcard principals see all snapshots, while scoped principals see only allowed scopes.

## Validation

Input schemas inherit from `StrictInput`:

- Unknown fields are rejected.
- Strings are stripped before validation.
- String lists are stripped, deduplicated, and reject empty values.
- Dates use strict `YYYY-MM-DD`.
- Transaction amounts and service prices must be positive.
- Item quantities cannot be negative.
- Item `in` and `out` adjustments must be greater than zero; absolute `adjustment` can be zero.

## Transaction Ingestion

Manual writes and external imports share `POST /api/transactions`.

External identity:

- `external_source` and `external_id` must be provided together.
- Reusing an existing pair returns the existing row.
- Reusing a soft-deleted external row restores it.

Duplicate and reconciliation behavior:

- Manual writes use amount, description, and date proximity.
- Tributary-style imports (`external_source="tributary"`) use amount and date only when trying to claim manually enriched rows.
- `force_create=true` bypasses duplicate/reconcile checks.
- `PATCH /api/transactions/{id}` is the minimal update path for enrichment and linking.

## Migrations

Alembic is the schema source of truth. The app does not call `Base.metadata.create_all()` on startup.

Before creating a migration:

```bash
.venv/bin/alembic current
.venv/bin/alembic heads
```

Current revision chain:

1. `a5d4361f28b5` baseline
2. `5724eca6fd16` soft delete and FK hardening
3. `7af2e8e2bb4f` agent tokens and actor attribution
4. `b3f1a2c4d5e6` recurring rules, later removed by hardening
5. `c1d2e3f4a5b6` remove recurring tables, add external identity, convert transaction amounts to cents
6. `d1e2f3a4b5c6` add `manually_enriched`
7. `e1f2a3b4c5d6` payment method constraint
8. `73fc7456f3d0` snapshots table

Historical migrations remain in the chain even when a feature has been removed.
