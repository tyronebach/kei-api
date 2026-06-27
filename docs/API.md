# Kei API Reference

Base URL for local development: `http://127.0.0.1:8081`

FastAPI app version: `0.2.0`

## Authentication

All `/api/*` endpoints require:

```http
Authorization: Bearer <token>
```

`/health`, `/docs`, `/redoc`, and `/openapi.json` are public.

Token resolution:

| Type | Resolution | Access |
|---|---|---|
| Agent token | SHA-256 bearer token hash matches `agent_tokens.token_hash` | Uses row `allowed_scopes` and `permissions` |
| Admin fallback | Bearer token exactly matches `KEI_API_TOKEN` | `allowed_scopes=["*"]`, `permissions=["read","write"]` |

Write endpoints require `write` permission. Missing or invalid tokens return `401`; read-only tokens on write endpoints return `403`.

## Scopes

Standard resources are scoped. Create and update paths validate submitted scopes against `KEI_VALID_SCOPES`.

Default configured scopes in code:

```json
["home", "salon", "woodwards", "synthhub", "household"]
```

Scope rules for standard scoped list endpoints:

- If `scope` is provided, the caller must be allowed to access that scope.
- If `scope` is omitted and the caller has `allowed_scopes=["*"]`, the query spans all scopes.
- If `scope` is omitted and the caller is scoped, the query is constrained to that caller's allowed scopes.

## Response Shapes

Most resource endpoints use an envelope:

```json
{"data": {"id": "..."}}
```

Most list endpoints return:

```json
{"data": [], "meta": {"count": 0, "total": 0}}
```

Exceptions in the current app:

- Snapshot endpoints return raw `SnapshotOut` objects or raw arrays because the router uses `response_model` directly.
- `/api/audit` returns a raw stats object.
- `DELETE /api/audit/soft-deleted` returns a raw `{ "deleted_count": N }` object.

Contract cleanup is future coordinated work. Do not change these live response
shapes until dependent services have been checked. Before any breaking envelope
migration, verify:

- CLI snapshot commands that parse raw snapshot responses.
- Household or system services that read or write snapshots.
- Audit consumers that parse raw stats or purge counts.
- Any deployed service still using `KEI_API_TOKEN` admin fallback auth.

The preferred migration path is optional versioned envelope endpoints. Client
hardening that accepts both raw and enveloped shapes is allowed only as a
tracked temporary transition during a coordinated rollout; the same change must
name the ADR or task and delete the dual parser after every dependency above is
confirmed migrated.

Errors are normalized:

```json
{
  "error": true,
  "status": 422,
  "message": "Validation error",
  "details": []
}
```

HTTP exceptions use the same shape without `details`.

## Common Fields

Standard scoped resources share:

| Field | Type | Notes |
|---|---|---|
| `id` | string | UUID hex |
| `scope` | string | Namespace |
| `created_by` | string or null | Agent that created the row |
| `updated_by` | string or null | Agent that last updated the row |
| `created_at` | integer | Unix epoch seconds |
| `updated_at` | integer | Unix epoch seconds |

`entities`, `transactions`, `items`, and `services` also include `meta`. `entities`, `transactions`, `items`, `services`, and `list_items` use soft delete through `deleted_at`, which is not exposed in normal output.

## Health

### `GET /health`

Public database connectivity check.

Success:

```json
{"status": "ok"}
```

Failure:

```json
{"status": "unhealthy"}
```

with HTTP `503`.

## Entities

Entities are contacts, clients, vendors, places, or other named references.

### `POST /api/entities`

Body:

```json
{
  "scope": "salon",
  "name": "Jane Doe",
  "type": "client",
  "phone": "555-1234",
  "email": "jane@example.com",
  "notes": "Prefers mornings",
  "tags": ["vip"],
  "meta": {"referral_source": "instagram"}
}
```

Required: `scope`, `name`.

### `GET /api/entities`

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `search` | Fuzzy search across `name`, `email`, `phone` |
| `type` | Exact entity type |
| `tag` | Exact value inside `tags` JSON array |
| `limit` | Default 50, max 200 |
| `offset` | Default 0 |

Search responses include `score`, `match_type`, and meta fields `query`, `confident`, and `best_match`.

### `GET /api/entities/insights`

Aggregate income transaction activity by entity.

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `inactive_days` | Include entities whose last visit is at least this many days ago; entities with no visits qualify |
| `min_visits` | Minimum income transaction count |
| `created_after` | Entity created after `YYYY-MM-DD` |
| `created_before` | Entity created before `YYYY-MM-DD` |
| `sort` | `last_visit`, `total_spend`, `visits`, or `name`; default `last_visit` |
| `limit` | Default 20, max 200 |

### `GET /api/entities/{entity_id}`

Returns one active entity.

### `GET /api/entities/{entity_id}/activity`

Returns entity details plus income transaction stats:

- `total_spend`
- `visit_count`
- `first_visit`
- `last_visit`
- `avg_spend`
- `by_category`
- `recent_transactions`

### `PUT /api/entities/{entity_id}`

Partial update. Same fields as create, all optional.

### `DELETE /api/entities/{entity_id}`

Soft delete.

```json
{"data": {"id": "...", "deleted": true}}
```

## Transactions

Transactions are income and expense ledger rows. API amounts are dollars; storage uses integer cents.

### `POST /api/transactions`

Body:

```json
{
  "scope": "salon",
  "type": "income",
  "amount": 80.0,
  "category": "haircut",
  "description": "Trim and style",
  "date": "2026-03-10",
  "entity_id": "abc123",
  "external_source": "tributary",
  "external_id": "plaid_txn_456",
  "tags": ["walk-in"],
  "payment_method": "etransfer",
  "manually_enriched": false,
  "meta": {},
  "force_create": false
}
```

Required: `scope`, `type`, `amount`, `category`, `date`.

Validation:

- `type` is `income` or `expense`.
- `amount` must be positive.
- `date` is strict `YYYY-MM-DD`.
- `payment_method` is `cash`, `etransfer`, `card`, `bank`, `cheque`, or `other`.
- `external_source` and `external_id` must be provided together.
- `entity_id`, if provided, must reference an active entity in the same scope.

Create response flags:

| Flag | Meaning |
|---|---|
| `created` | New row inserted |
| `matched` | High-confidence duplicate found; no row inserted |
| `probable_match` | Medium-confidence duplicate warning; row still inserted |
| `match_score` | Duplicate score paired with `probable_match` |
| `reconciled` | External import claimed an existing manually enriched row |
| `enriched` | Manual write updated an existing Tributary row |
| `restored` | Reused external identity restored a soft-deleted row |

Duplicate behavior:

- Manual writes without `external_source` score amount, description, and date proximity.
- `external_source="tributary"` writes score amount and date against manually enriched unclaimed rows.
- Reusing an existing `(external_source, external_id)` in the same scope returns or restores that row instead of inserting.
- Reusing an existing `(external_source, external_id)` from another scope returns `409` without exposing that row.
- `force_create=true` skips duplicate/reconcile checks.

### `GET /api/transactions`

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `type` | `income` or `expense` |
| `category` | Comma-separated category names |
| `entity_id` | Linked entity ID |
| `from` | Start date, inclusive, strict `YYYY-MM-DD` |
| `to` | End date, inclusive, strict `YYYY-MM-DD` |
| `payment_method` | Exact payment method |
| `external_source` | Exact external source |
| `external_id` | Exact external ID |
| `bank` | `meta.bank` value |
| `account_mask` | `meta.account_mask` value |
| `sort` | `date`, `created_at`, or `amount`; all descending |
| `limit` | Default 50, max 200 |
| `offset` | Default 0 |

### `GET /api/transactions/{transaction_id}`

Returns one active transaction.

### `PUT /api/transactions/{transaction_id}`

Partial update. Same writable fields as create except `force_create`. If `amount` is provided it is converted from dollars to cents.

### `PATCH /api/transactions/{transaction_id}`

Minimal partial update, intended for enrichment/linking. If `description` or `entity_id` is added and `manually_enriched` is not explicitly supplied, the server sets `manually_enriched=true`.

### `DELETE /api/transactions/{transaction_id}`

Soft delete.

## Items

Inventory items with stock quantities and movement history.

### `POST /api/items`

Body:

```json
{
  "scope": "salon",
  "name": "Shampoo 500ml",
  "category": "supplies",
  "quantity": 24,
  "unit": "bottle",
  "reorder_threshold": 5,
  "notes": "Brand X",
  "tags": ["hair-care"],
  "meta": {}
}
```

Required: `scope`, `name`. `quantity` defaults to `0`; `unit` defaults to `unit`.

### `GET /api/items`

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `search` | Fuzzy search across `name`, `category`, `notes` |
| `category` | Exact category |
| `limit` | Default 50, max 200 |
| `offset` | Default 0 |

### `GET /api/items/low-stock`

Returns active items with `reorder_threshold` set and `quantity <= reorder_threshold`.

Query params: `scope`.

### `GET /api/items/{item_id}`

Returns one active item.

### `GET /api/items/{item_id}/movements`

Movement history for an item.

Query params: `limit` default 50 max 200, `offset` default 0.

### `POST /api/items/{item_id}/adjust`

Body:

```json
{
  "type": "out",
  "quantity": 2,
  "reason": "Used for client",
  "transaction_id": "txn_abc"
}
```

`type` is:

- `in`: add quantity
- `out`: subtract quantity; returns `409` if stock is insufficient
- `adjustment`: set absolute quantity

If `transaction_id` is supplied, it must reference an active transaction the caller can access in the same scope as the item.

Response:

```json
{"data": {"id": "..."}, "meta": {"movement_id": "..."}}
```

### `PUT /api/items/{item_id}`

Partial update.

### `DELETE /api/items/{item_id}`

Soft delete.

## Services

Service catalog entries with price and optional duration.

### `POST /api/services`

Body:

```json
{
  "scope": "salon",
  "name": "Haircut",
  "category": "hair",
  "price": 45.0,
  "duration_minutes": 30,
  "notes": "Includes wash",
  "tags": ["popular"],
  "meta": {}
}
```

Required: `scope`, `name`, `price`.

### `GET /api/services`

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `category` | Exact category |
| `tag` | Exact value inside `tags` JSON array |
| `limit` | Default 50, max 200 |
| `offset` | Default 0 |

Results are ordered by service name.

### `GET /api/services/{service_id}`

Returns one active service.

### `PUT /api/services/{service_id}`

Partial update.

### `DELETE /api/services/{service_id}`

Soft delete.

## Lists

List items are lightweight checklist or note rows grouped by a free-form `list` name.

### `GET /api/lists`

Returns distinct `(scope, list)` pairs with counts.

Query params: `scope`.

### `GET /api/lists/items`

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `list` | Exact list name |
| `checked` | Boolean checked state |
| `limit` | Default 50, max 200 |
| `offset` | Default 0 |

Results are ordered by `position`, then `created_at`.

### `POST /api/lists/items`

Body:

```json
{
  "scope": "home",
  "list": "groceries",
  "content": "Milk",
  "position": 1
}
```

Required: `scope`, `list`, `content`. If `position` is omitted, the server appends to the end of that scoped list.

### `PUT /api/lists/items/{item_id}`

Partial update fields: `content`, `checked`, `position`, `list`.

### `DELETE /api/lists/items/{item_id}`

Soft delete one list item.

### `DELETE /api/lists`

Soft clear a list.

Required query params: `scope`, `list`.

Optional query param: `checked_only`, default `false`.

## Summary

Financial aggregate endpoints. Amounts are returned in dollars. All summary endpoints enforce the standard scope rules.

Common query params for `/api/summary`, `/trends`, `/by-scope`, `/by-day`, and `/by-category`:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `period` | `today`, `week`, `month`, `year`, `custom`; default `month` |
| `from` | Required for `period=custom` |
| `to` | Required for `period=custom` |
| `payment_method` | Exact payment method |
| `source` | `bank`, `cash`, `agent`, or `all` |

Invalid `period`, `source`, or by-category `type` values return `422`.

Source mapping:

- `bank`: `external_source == "tributary"`
- `cash`: `payment_method == "cash"`
- `agent`: `external_source IS NULL` and `payment_method != "cash"`; rows with null `payment_method` do not match this filter in the current SQL query
- `all` or omitted: no source filter

### `GET /api/summary`

Returns period totals, top income and expense categories, client metrics, and inventory alert count.

### `GET /api/summary/trends`

Compares the selected period to the previous period of the same length.

### `GET /api/summary/by-scope`

Groups income, expenses, and profit by scope.

### `GET /api/summary/by-day`

Groups income by weekday for the selected period.

### `GET /api/summary/by-category`

Groups by `(category, type)`, sorted by total amount descending.

Additional params:

| Param | Notes |
|---|---|
| `type` | Optional `income` or `expense` |
| `limit` | Default 20, max 100 |

### `GET /api/summary/by-month`

Groups income, expenses, and profit by calendar month. Defaults to roughly the last 12 months if `from` and `to` are omitted and fills missing months with zero totals.

Query params: `scope`, `from`, `to`, `payment_method`, `source`.

## Snapshots

Snapshots store arbitrary financial snapshot blobs keyed by `scope` and `date`.

Current response shape: raw objects or arrays, not `{"data": ...}` envelopes.

Snapshot reads and writes enforce the caller's `allowed_scopes`. When `GET /api/snapshots` omits `scope`, wildcard tokens see all snapshots and scoped tokens see only allowed scopes.

### `POST /api/snapshots`

Status: `201`

Body:

```json
{
  "scope": "household",
  "date": "2026-03-27",
  "data": {"net_worth": {}, "accounts": []}
}
```

If a snapshot already exists for the same `(scope, date)`, the `data` and `created_by` fields are replaced.

### `GET /api/snapshots`

Returns a raw array of `SnapshotOut`.

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter |
| `from` | Start date, inclusive, strict `YYYY-MM-DD` |
| `to` | End date, inclusive, strict `YYYY-MM-DD` |
| `limit` | Default 50, max 500 |
| `offset` | Default 0 |

### `GET /api/snapshots/latest`

Returns the most recent raw `SnapshotOut` for `scope`, default `household`.

### `GET /api/snapshots/{snapshot_id}`

Returns one raw `SnapshotOut`.

## Audit

Audit endpoints currently inspect transaction rows only.

### `GET /api/audit`

Returns a raw stats object:

```json
{
  "soft_deleted_count": 0,
  "content_duplicate_count": 0,
  "active_count": 0
}
```

`content_duplicate_count` counts duplicate active transaction groups by `(scope, date, amount, description)`.

Query params:

| Param | Notes |
|---|---|
| `scope` | Optional scope filter; omitted scope follows the caller's allowed scopes |

### `DELETE /api/audit/soft-deleted`

Requires wildcard `write` access. Permanently deletes soft-deleted transactions and returns:

```json
{"deleted_count": 0}
```

## Error Codes

| Status | Meaning |
|---|---|
| `401` | Missing or invalid bearer token |
| `403` | Scope access denied or token lacks `write` |
| `404` | Resource not found or soft-deleted |
| `409` | Conflict, used for insufficient stock and cross-scope external identity collisions |
| `422` | Validation error |
| `503` | Health check database failure |

## Generated Docs

FastAPI exposes generated docs while the app is running:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`
