# Kei API Reference

**Base URL:** `http://localhost:8081` (local dev) or your deployed host
**Version:** 0.2.0

---

## Authentication

All endpoints (except `/health`) require a Bearer token.

```
Authorization: Bearer <token>
```

**Token types:**

| Type | How it works | Capabilities |
|------|-------------|--------------|
| Admin token | Matches `KEI_API_TOKEN` env var exactly | All scopes (`*`), read + write |
| Agent token | SHA-256 hash matched against `agent_tokens` table | Scoped access, configurable permissions |

A read-only agent token can only call GET endpoints. Write endpoints (POST, PUT, PATCH, DELETE) return `403` for tokens without `write` permission.

---

## Scopes

Every resource is namespaced by a `scope` string. Agents can only access scopes they are authorized for. Valid scopes are configured via `KEI_VALID_SCOPES` (default: `home`, `salon`, `woodwards`, `synthhub`).

Passing an invalid scope returns `422`. Accessing a scope outside the agent's allowed list returns `403`.

---

## Response Format

**Success (single resource):**
```json
{
  "data": { ... }
}
```

**Success (list):**
```json
{
  "data": [ ... ],
  "meta": { "count": 10, "total": 42 }
}
```

**Error:**
```json
{
  "error": true,
  "status": 422,
  "message": "Validation error",
  "details": [ ... ]
}
```

---

## Common Query Parameters

These appear across multiple list endpoints:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | string | — | Filter by scope |
| `limit` | int | 50 | Max results (max 200) |
| `offset` | int | 0 | Pagination offset |

---

## Common Fields

All scoped resources share these output fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID hex identifier |
| `scope` | string | Namespace |
| `meta` | object \| null | Arbitrary JSON extension point |
| `created_by` | string \| null | Agent ID that created the record |
| `updated_by` | string \| null | Agent ID that last updated the record |
| `created_at` | int | Unix epoch timestamp |
| `updated_at` | int | Unix epoch timestamp |

All resources use **soft delete** — `DELETE` sets a `deleted_at` timestamp rather than removing the row.

---

## Health

### `GET /health`

No authentication required. Tests database connectivity.

**Response:**
```json
{ "status": "ok" }
```

Returns `503` with `{ "status": "unhealthy" }` if the database is unreachable.

---

## Entities

Contacts, clients, vendors — any named entity linked to transactions.

### `POST /api/entities`

Create a new entity.

**Body:**
```json
{
  "scope": "salon",
  "name": "Jane Doe",
  "type": "client",
  "phone": "555-1234",
  "email": "jane@example.com",
  "notes": "Prefers mornings",
  "tags": ["vip", "regular"],
  "meta": { "referral_source": "instagram" }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `scope` | string | yes | Must be a valid scope |
| `name` | string | yes | Min length 1 |
| `type` | string | no | Free-form (e.g. `client`, `vendor`) |
| `phone` | string | no | |
| `email` | string | no | |
| `notes` | string | no | |
| `tags` | string[] | no | Deduplicated, no empty strings |
| `meta` | object | no | |

**Response:** `{ "data": EntityOut }`

---

### `GET /api/entities`

List entities with optional search and filters.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |
| `search` | string | Fuzzy search across name, email, phone |
| `type` | string | Filter by entity type |
| `tag` | string | Filter by tag (exact match within JSON array) |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

**Without search:** Returns `{ "data": [EntityOut], "meta": { "count", "total" } }` ordered by `updated_at` desc.

**With search:** Returns scored results:
```json
{
  "data": [
    {
      "id": "...",
      "name": "Jane Doe",
      "score": 0.92,
      "match_type": "exact",
      ...
    }
  ],
  "meta": {
    "count": 1,
    "total": 1,
    "query": "jane",
    "confident": true,
    "best_match": "abc123"
  }
}
```

`match_type` values: `exact`, `fuzzy`, `phonetic`, `partial`

---

### `GET /api/entities/insights`

Aggregate entity activity — visit counts, spend totals, sorted/filtered.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | string | — | Filter by scope |
| `inactive_days` | int | — | Only entities whose last visit was >= N days ago |
| `min_visits` | int | — | Only entities with >= N visits |
| `created_after` | string | — | YYYY-MM-DD |
| `created_before` | string | — | YYYY-MM-DD |
| `sort` | string | `last_visit` | One of: `last_visit`, `total_spend`, `visits`, `name` |
| `limit` | int | 20 | Max 200 |

**Response item shape:**
```json
{
  "id": "...",
  "scope": "salon",
  "name": "Jane Doe",
  "type": "client",
  "visit_count": 12,
  "total_spend": 840.00,
  "last_visit": "2026-03-10"
}
```

---

### `GET /api/entities/{entity_id}`

Get a single entity by ID.

**Response:** `{ "data": EntityOut }`

Returns `404` if not found or soft-deleted. Returns `403` if out of scope.

---

### `GET /api/entities/{entity_id}/activity`

Detailed activity for an entity — spend stats, category breakdown, recent transactions.

**Response:**
```json
{
  "data": {
    "id": "...",
    "name": "Jane Doe",
    "total_spend": 840.00,
    "visit_count": 12,
    "first_visit": "2025-06-15",
    "last_visit": "2026-03-10",
    "avg_spend": 70.00,
    "by_category": [
      { "category": "haircut", "total": 600.00, "count": 8 }
    ],
    "recent_transactions": [
      {
        "id": "...",
        "type": "income",
        "amount": 80.00,
        "category": "haircut",
        "description": "Trim + style",
        "date": "2026-03-10",
        "payment_method": "etransfer"
      }
    ]
  }
}
```

---

### `PUT /api/entities/{entity_id}`

Update an entity. Only fields included in the body are changed (exclude_unset).

**Body:** Same fields as `EntityCreate`, all optional.

**Response:** `{ "data": EntityOut }`

---

### `DELETE /api/entities/{entity_id}`

Soft-delete an entity.

**Response:**
```json
{ "data": { "id": "...", "deleted": true } }
```

---

## Transactions

Financial records — income and expenses. Amounts are **dollars** in the API (stored as integer cents internally).

### `POST /api/transactions`

Create a transaction with built-in deduplication and reconciliation.

**Body:**
```json
{
  "scope": "salon",
  "type": "income",
  "amount": 80.00,
  "category": "haircut",
  "description": "Trim + style for Jane",
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

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `scope` | string | yes | |
| `type` | `"income"` \| `"expense"` | yes | |
| `amount` | float | yes | Dollars, must be > 0 |
| `category` | string | yes | |
| `description` | string | no | |
| `date` | string | yes | YYYY-MM-DD |
| `entity_id` | string | no | FK to entities (must match scope) |
| `external_source` | string | no | Must pair with `external_id` |
| `external_id` | string | no | Must pair with `external_source` |
| `tags` | string[] | no | |
| `payment_method` | string | no | `cash`, `etransfer`, `card`, `bank`, `cheque`, `other` |
| `manually_enriched` | bool | no | Auto-inferred if description or entity_id provided |
| `meta` | object | no | |
| `force_create` | bool | no | Skip duplicate checking |

**Deduplication behavior:**

The response includes extra flags depending on what happened:

| Flag | Meaning |
|------|---------|
| `"created": true` | New row inserted |
| `"reconciled": true` | Tributary import matched & claimed an existing manual row |
| `"enriched": true` | Manual write enriched an existing bank import |
| `"matched": true` | High-confidence duplicate found (not created) |
| `"restored": true` | Re-submitted external_id restored a soft-deleted row |
| `"probable_match"` | Medium-confidence match found — row was still created, but a warning is returned with the probable duplicate |

**Idempotency:** Re-submitting the same `(external_source, external_id)` pair returns the existing row without creating a duplicate.

---

### `GET /api/transactions`

List transactions with filters and sorting.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |
| `type` | string | `income` or `expense` |
| `category` | string | Comma-separated categories |
| `entity_id` | string | Filter by linked entity |
| `from` | string | Start date (YYYY-MM-DD), inclusive |
| `to` | string | End date (YYYY-MM-DD), inclusive |
| `payment_method` | string | Filter by payment method |
| `external_source` | string | Filter by external source |
| `external_id` | string | Filter by external ID |
| `sort` | string | `date` (default), `created_at`, `amount` — all descending |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

**Response:** `{ "data": [TransactionOut], "meta": { "count", "total" } }`

---

### `GET /api/transactions/{transaction_id}`

**Response:** `{ "data": TransactionOut }`

---

### `PUT /api/transactions/{transaction_id}`

Full update. All provided fields are applied.

**Body:** Same fields as `TransactionCreate` minus `force_create`, all optional. Amount in dollars.

---

### `PATCH /api/transactions/{transaction_id}`

Partial update — only explicitly sent fields are changed. Used for enrichment (linking entity_id, adding description to bank imports, etc.).

Auto-infers `manually_enriched = true` when description or entity_id is added via PATCH.

**Body:** Same shape as PUT.

---

### `DELETE /api/transactions/{transaction_id}`

Soft-delete.

**Response:** `{ "data": { "id": "...", "deleted": true } }`

---

### TransactionOut shape

```json
{
  "id": "...",
  "scope": "salon",
  "type": "income",
  "amount": 80.00,
  "category": "haircut",
  "description": "Trim + style",
  "date": "2026-03-10",
  "entity_id": "abc123",
  "external_source": "tributary",
  "external_id": "plaid_txn_456",
  "tags": ["walk-in"],
  "payment_method": "etransfer",
  "manually_enriched": true,
  "meta": {},
  "created_by": "admin",
  "updated_by": "admin",
  "created_at": 1741564800,
  "updated_at": 1741564800
}
```

---

## Items

Inventory items with stock tracking and movement history.

### `POST /api/items`

**Body:**
```json
{
  "scope": "salon",
  "name": "Shampoo 500ml",
  "category": "supplies",
  "quantity": 24,
  "unit": "bottle",
  "reorder_threshold": 5,
  "notes": "Brand X preferred",
  "tags": ["hair-care"],
  "meta": {}
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `scope` | string | yes | |
| `name` | string | yes | Min length 1 |
| `category` | string | no | |
| `quantity` | float | no | Default 0, must be >= 0 |
| `unit` | string | no | Default `"unit"` |
| `reorder_threshold` | float | no | Triggers low-stock alerts |
| `notes` | string | no | |
| `tags` | string[] | no | |
| `meta` | object | no | |

---

### `GET /api/items`

List items with optional fuzzy search.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |
| `search` | string | Fuzzy search across name, category, notes |
| `category` | string | Filter by category |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

Search response includes `score`, `match_type`, `confident`, `best_match` (same shape as entity search).

---

### `GET /api/items/low-stock`

Returns items where `quantity <= reorder_threshold`, ordered by quantity ascending.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |

**Response:** `{ "data": [ItemOut], "meta": { "count" } }`

---

### `GET /api/items/{item_id}`

**Response:** `{ "data": ItemOut }`

---

### `GET /api/items/{item_id}/movements`

Stock movement history for an item.

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

**Response item shape:**
```json
{
  "id": "...",
  "item_id": "...",
  "type": "in",
  "quantity": 12.0,
  "reason": "Restock delivery",
  "transaction_id": null,
  "created_at": 1741564800
}
```

---

### `POST /api/items/{item_id}/adjust`

Adjust item quantity — add stock, remove stock, or set absolute quantity.

**Body:**
```json
{
  "type": "in",
  "quantity": 12,
  "reason": "Restock delivery",
  "transaction_id": "txn_abc"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | `"in"` \| `"out"` \| `"adjustment"` | yes | |
| `quantity` | float | yes | > 0 for `in`/`out`, >= 0 for `adjustment` |
| `reason` | string | no | Human-readable reason |
| `transaction_id` | string | no | Link to related transaction |

**Behavior:**
- `in` — adds to current quantity
- `out` — subtracts from current quantity; returns `409` if insufficient stock
- `adjustment` — sets quantity to the given value

**Response:** `{ "data": ItemOut, "meta": { "movement_id": "..." } }`

---

### `PUT /api/items/{item_id}`

Update item fields. Same shape as create body, all optional.

---

### `DELETE /api/items/{item_id}`

Soft-delete.

---

## Services

Service catalog — offered services with pricing and duration.

### `POST /api/services`

**Body:**
```json
{
  "scope": "salon",
  "name": "Haircut",
  "category": "hair",
  "price": 45.00,
  "duration_minutes": 30,
  "notes": "Includes wash",
  "tags": ["popular"],
  "meta": {}
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `scope` | string | yes | |
| `name` | string | yes | Min length 1 |
| `category` | string | no | |
| `price` | float | yes | Must be > 0 |
| `duration_minutes` | int | no | |
| `notes` | string | no | |
| `tags` | string[] | no | |
| `meta` | object | no | |

---

### `GET /api/services`

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |
| `category` | string | Filter by category |
| `tag` | string | Filter by tag (exact match within JSON array) |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

Results ordered by name ascending.

---

### `GET /api/services/{service_id}`

**Response:** `{ "data": ServiceOut }`

---

### `PUT /api/services/{service_id}`

Update service. Same shape as create body, all optional.

---

### `DELETE /api/services/{service_id}`

Soft-delete.

---

## Lists

Checklist/to-do items grouped by named lists. Lists are free-form — no upfront creation needed.

### `GET /api/lists`

Get list summaries — distinct (scope, list) pairs with counts.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |

**Response:**
```json
{
  "data": [
    {
      "scope": "home",
      "list": "groceries",
      "total": 8,
      "checked": 3,
      "unchecked": 5
    }
  ],
  "meta": { "count": 1 }
}
```

---

### `GET /api/lists/items`

List individual items across lists.

| Param | Type | Description |
|-------|------|-------------|
| `scope` | string | Filter by scope |
| `list` | string | Filter by list name |
| `checked` | bool | Filter by checked status |
| `limit` | int | Default 50, max 200 |
| `offset` | int | Default 0 |

Results ordered by position asc, then created_at asc.

---

### `POST /api/lists/items`

Create a list item.

**Body:**
```json
{
  "scope": "home",
  "list": "groceries",
  "content": "Milk 2L",
  "position": 1
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `scope` | string | yes | |
| `list` | string | yes | List name (free-form) |
| `content` | string | yes | Min length 1 |
| `position` | int | no | Auto-assigned if omitted (max + 1) |

---

### `PUT /api/lists/items/{item_id}`

Update a list item.

**Body:**
```json
{
  "content": "Milk 1L",
  "checked": true,
  "position": 2,
  "list": "groceries"
}
```

All fields optional.

---

### `DELETE /api/lists/items/{item_id}`

Soft-delete a single list item.

---

### `DELETE /api/lists`

Clear an entire list (or just checked items).

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | string | yes | |
| `list` | string | yes | List name |
| `checked_only` | bool | no | Default `false`. If `true`, only delete checked items |

**Response:**
```json
{ "data": { "list": "groceries", "scope": "home", "deleted_count": 3 } }
```

---

## Summary

Aggregate financial analytics. All amounts in dollars.

### Common Summary Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | string | — | Filter by scope |
| `period` | string | `month` | `today`, `week`, `month`, `year`, `custom` |
| `from` | string | — | YYYY-MM-DD (required if `period=custom`) |
| `to` | string | — | YYYY-MM-DD (required if `period=custom`) |
| `payment_method` | string | — | Filter by payment method |
| `source` | string | — | `bank`, `cash`, `agent`, `all` |

**Period resolution:**
- `today` — current day
- `week` — Monday through today
- `month` — 1st of current month through today
- `year` — Jan 1 through today
- `custom` — requires `from` and `to`

**Source filter mapping:**
- `bank` — `external_source == "tributary"`
- `cash` — `payment_method == "cash"`
- `agent` — no external source and not cash
- `all` — no filter

---

### `GET /api/summary`

Period summary with income/expense totals, top categories, client metrics, and inventory alerts.

**Response:**
```json
{
  "data": {
    "period": { "from": "2026-03-01", "to": "2026-03-17" },
    "income": { "total": 4200.00, "count": 52 },
    "expenses": { "total": 1100.00, "count": 15 },
    "profit": 3100.00,
    "top_income": [
      { "category": "haircut", "total": 2800.00, "count": 35 }
    ],
    "top_expenses": [
      { "category": "supplies", "total": 400.00, "count": 3 }
    ],
    "clients": {
      "active": 28,
      "new": 5,
      "returning": 23
    },
    "inventory_alerts": 2
  }
}
```

---

### `GET /api/summary/trends`

Compare current period vs previous period of same length.

**Response:**
```json
{
  "data": {
    "current": {
      "period": { "from": "2026-03-01", "to": "2026-03-17" },
      "income": 4200.00,
      "expenses": 1100.00,
      "profit": 3100.00
    },
    "previous": {
      "period": { "from": "2026-02-12", "to": "2026-02-28" },
      "income": 3800.00,
      "expenses": 950.00,
      "profit": 2850.00
    },
    "change": {
      "income": { "amount": 400.00, "percent": 10.5 },
      "expenses": { "amount": 150.00, "percent": 15.8 },
      "profit": { "amount": 250.00, "percent": 8.8 }
    },
    "trend": "up"
  }
}
```

`trend` values: `up` (>5% income increase), `down` (<-5%), `stable` (within +-5%)

---

### `GET /api/summary/by-scope`

Income/expense totals grouped by scope.

**Response:**
```json
{
  "data": {
    "period": { "from": "2026-03-01", "to": "2026-03-17" },
    "scopes": [
      {
        "scope": "salon",
        "income": { "total": 3200.00, "count": 40 },
        "expenses": { "total": 800.00, "count": 10 },
        "profit": 2400.00
      }
    ]
  },
  "meta": { "count": 2 }
}
```

---

### `GET /api/summary/by-day`

Income totals by day of week for the given period.

**Response:**
```json
{
  "data": {
    "period": { "from": "2026-03-01", "to": "2026-03-17" },
    "days": [
      { "day": "Monday", "total": 650.00, "count": 8 },
      { "day": "Tuesday", "total": 720.00, "count": 9 },
      { "day": "Wednesday", "total": 580.00, "count": 7 },
      { "day": "Thursday", "total": 690.00, "count": 8 },
      { "day": "Friday", "total": 810.00, "count": 10 },
      { "day": "Saturday", "total": 450.00, "count": 6 },
      { "day": "Sunday", "total": 0.00, "count": 0 }
    ],
    "busiest": "Friday"
  }
}
```

---

### `GET /api/summary/by-month`

Monthly income/expense breakdown. Defaults to last 12 months. Fills months with no data as zeros.

| Param | Type | Description |
|-------|------|-------------|
| `from` | string | Start date (defaults to ~12 months ago) |
| `to` | string | End date (defaults to today) |
| `scope`, `payment_method`, `source` | | Same as other summary endpoints |

**Response:**
```json
{
  "data": {
    "period": { "from": "2025-03-17", "to": "2026-03-17" },
    "months": [
      {
        "month": "2025-03",
        "income": 3200.00,
        "expenses": 900.00,
        "profit": 2300.00,
        "income_count": 38,
        "expense_count": 12
      }
    ]
  },
  "meta": { "count": 13 }
}
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 401 | Invalid or missing bearer token |
| 403 | Token lacks scope access or write permission |
| 404 | Resource not found or soft-deleted |
| 409 | Conflict (e.g. insufficient stock for item adjustment) |
| 422 | Validation error — invalid scope, bad date format, missing required fields |
| 503 | Database unreachable (health check only) |

---

## OpenAPI / Swagger

FastAPI auto-generates interactive docs:

- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`
- **OpenAPI JSON:** `GET /openapi.json`
