# Kei API (経) - Implementation Design

## Status

- Status: Implemented
- Last updated: 2026-02-18
- Scope: current production architecture and API behavior

This file replaces the earlier MVP draft design and documents what is actually implemented now.

## Overview

Kei API is an agent-first FastAPI + SQLite service for scoped financial and operational data.

Primary design goals:
- predictable JSON responses for LLM agents
- strict validation at write boundaries
- low operational complexity (SQLite + Docker)
- secure multi-agent access using scoped tokens

## Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (sync endpoints) |
| Database | SQLite (WAL mode) |
| ORM | SQLAlchemy 2.x |
| Validation | Pydantic 2.x |
| Search | rapidfuzz + Soundex |
| Migrations | Alembic |
| Deployment | Docker / Docker Compose |

## Data Model

### Core tables

- `entities`
- `transactions`
- `items`
- `item_movements`
- `services`
- `list_items`
- `agent_tokens`

### Cross-cutting model rules

- IDs are UUID hex strings.
- Timestamps are Unix epoch integers.
- `scope` is required on scoped resources.
- `deleted_at` implements soft delete on scoped resources:
  - `entities`, `transactions`, `items`, `services`, `list_items`
- `created_by` and `updated_by` are stored on scoped resources for audit.
- Foreign keys:
  - `transactions.entity_id -> entities.id` (`ON DELETE SET NULL`)
  - `item_movements.item_id -> items.id` (`ON DELETE CASCADE`)
  - `item_movements.transaction_id -> transactions.id` (`ON DELETE SET NULL`)

## Auth and Authorization

### Principal model

Requests are authenticated into an `AgentPrincipal`:
- `agent_id`
- `allowed_scopes` (example: `["salon"]` or `["*"]`)
- `permissions` (example: `["read","write"]`)

### Token resolution

1. Hash bearer token with SHA-256.
2. Match `agent_tokens.token_hash`.
3. If no match, fallback to `KEI_API_TOKEN` as admin wildcard principal.
4. Otherwise return `401 Invalid token`.

### Enforcement model

- All `/api/*` endpoints require auth.
- Read endpoints enforce scope access.
- Write endpoints require both:
  - scope access
  - `write` permission
- Write scopes are validated against `KEI_VALID_SCOPES`.

## Validation and Integrity Rules

- Unknown input fields are rejected (`extra="forbid"`).
- Strings are trimmed.
- Tag arrays are normalized:
  - trimmed
  - empty strings rejected
  - deduplicated
- Date strings are strict `YYYY-MM-DD`.
- `TransactionCreate.amount` and `ServiceCreate.price` must be `> 0`.
- Item quantity constraints:
  - create/update quantity `>= 0`
  - adjust:
    - `in` and `out` require `> 0`
    - `adjustment` allows `>= 0`

### Stock adjustment concurrency

`POST /api/items/{id}/adjust` uses guarded SQL `UPDATE` statements instead of Python read-modify-write.
- prevents lost updates under concurrent writes
- returns `409` for insufficient stock
- writes movement log in same transaction

## API Surface (Current)

### Entities

- `POST /api/entities`
- `GET /api/entities`
- `GET /api/entities/{entity_id}`
- `PUT /api/entities/{entity_id}`
- `DELETE /api/entities/{entity_id}` (soft delete)
- `GET /api/entities/{entity_id}/activity`
- `GET /api/entities/insights`

### Transactions

- `POST /api/transactions`
- `GET /api/transactions`
- `GET /api/transactions/{transaction_id}`
- `PUT /api/transactions/{transaction_id}`
- `DELETE /api/transactions/{transaction_id}` (soft delete)

#### Fuzzy duplicate detection (`POST /api/transactions`)

Manual writes (no `external_source`) run fuzzy dedup against transactions within a ±3-day window using amount (40%), description (40%), and date proximity (20%) weights.

**Response shapes:**

| Condition | `matched` | `created` | `probable_match` | `data` |
|-----------|-----------|-----------|------------------|--------|
| Score ≥ 85 (duplicate) | `true` | — | — | existing tx |
| Score 70–84 (probable) | — | `true` | existing tx | — |
| Score < 70 (new) | — | `true` | — | new tx |

**`force_create` field:** Set `force_create: true` in the request body to bypass dedup entirely and always insert a new row. Also bypassed for Tributary writes (`external_source` set).

### Items

- `POST /api/items`
- `GET /api/items`
- `GET /api/items/{item_id}`
- `PUT /api/items/{item_id}`
- `DELETE /api/items/{item_id}` (soft delete)
- `GET /api/items/low-stock`
- `GET /api/items/{item_id}/movements`
- `POST /api/items/{item_id}/adjust`

### Services

- `POST /api/services`
- `GET /api/services` (supports `scope`, `category`, `tag`)
- `GET /api/services/{service_id}`
- `PUT /api/services/{service_id}`
- `DELETE /api/services/{service_id}` (soft delete)

### Lists

- `GET /api/lists`
- `GET /api/lists/items`
- `POST /api/lists/items`
- `PUT /api/lists/items/{item_id}`
- `DELETE /api/lists/items/{item_id}` (soft delete)
- `DELETE /api/lists` (soft clear)

### Summary

- `GET /api/summary`
- `GET /api/summary/trends`
- `GET /api/summary/by-day`
- `GET /api/summary/by-scope`

### Health

- `GET /health`
  - `200 {"status":"ok"}` when DB is reachable
  - `503 {"status":"unhealthy"}` when DB check fails

## Response Contracts

Success response patterns:
- object: `{"data": {...}}`
- collection: `{"data": [...], "meta": {...}}`

Error response patterns:

HTTP exceptions:
```json
{
  "error": true,
  "status": 403,
  "message": "No access to scope 'home'"
}
```

Validation errors:
```json
{
  "error": true,
  "status": 422,
  "message": "Validation error",
  "details": [...]
}
```

## Migrations and Startup

- Alembic is the source of truth for schema changes.
- Application does not run `create_all()` at startup.
- Container startup sequence:
  1. `alembic upgrade head`
  2. start Uvicorn

Current revision chain:
- `a5d4361f28b5` baseline
- `5724eca6fd16` soft delete + FK hardening
- `7af2e8e2bb4f` agent tokens + attribution

## Operational Practices

- Deploy/run commands are documented in `DEPLOY.md`.
- Backups use SQLite `.backup` (WAL-safe).
- Rollback strategy: restore known-good backup and restart.
- Test suite exists and should be run before deployment:
  - `pytest -q`

## Known Boundaries

- SQLite is intentionally retained (low traffic, trusted environment).
- No async endpoint requirement.
- No frontend concerns in API design.
- `meta` remains flexible JSON by design.
