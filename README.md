# Kei API (経)

Agent-first data API designed for LLM assistants. Five resource types, smart search, pre-computed aggregates. The API does the heavy lifting so the agent can focus on understanding the user.

Domain-agnostic — works for salon management, household tracking, small business ops, whatever. The `scope` field namespaces everything so one API serves multiple contexts. The `meta` JSON field on every table handles domain-specific data without schema changes.

## Setup

```bash
# Local dev
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # edit KEI_API_TOKEN
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --port 8081 --reload

# Docker
docker build -t kei-api .
docker run -p 8081:8081 -e KEI_API_TOKEN=your-secret -v kei-data:/app/data kei-api
```

Deployment and operations runbook: `DEPLOY.md`.

⚠️ On startup, Kei API now fails fast if `KEI_API_TOKEN` is left as `changeme` (unless `KEI_ALLOW_INSECURE_DEFAULT_TOKEN=true`). This prevents accidental insecure exposure.

## Integrated CLI

This repo includes the Kei CLI at `cli/kei` for agent-facing commands.

```bash
cd cli/kei
python3 -m venv .venv
.venv/bin/pip install -e .

# point CLI at local API
export KEI_API_BASE=http://127.0.0.1:8081
export KEI_API_TOKEN=test-token

# quick checks
.venv/bin/python -m kei.cli health
.venv/bin/python -m kei.cli -s salon summary
```

CLI integration test script:

```bash
cd cli/kei/scripts
./integration_check.sh
```

## Auth

All `/api/*` endpoints require a bearer token.

```
Authorization: Bearer <token>
```

Auth resolution order:
1. `agent_tokens.token_hash` match (SHA-256 of bearer token) -> scoped principal
2. Fallback to legacy `KEI_API_TOKEN` -> admin principal (`allowed_scopes=["*"]`)

Write endpoints require `write` permission. Read endpoints always enforce scope access.
The `/health` endpoint is public.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `KEI_API_TOKEN` | `changeme` | Legacy admin fallback token. **Must be overridden in real deployments** |
| `KEI_DATABASE_URL` | `sqlite:///./data/kei.db` | SQLite database path |
| `KEI_VALID_SCOPES` | `["home","salon","woodwards","synthhub"]` | Allowed scopes (JSON list). Put your real scope set in local `.env` (not committed) |
| `KEI_CORS_ORIGINS` | `[]` | Browser allowlist (JSON array). Keep empty unless you need frontend access |
| `KEI_ALLOW_INSECURE_DEFAULT_TOKEN` | `false` | Local-only escape hatch to permit default `changeme` token |

## Scope

Every record has a `scope` field. Scope is required on creates and validated against `KEI_VALID_SCOPES`.
For list endpoints, scope behavior depends on the caller's token:
- wildcard agents (`allowed_scopes=["*"]`) can omit `scope` to query across all scopes
- scoped agents only see their own allowed scopes when `scope` is omitted

```
POST /api/transactions  {"scope": "salon", ...}   # required on create
GET  /api/transactions?scope=salon                 # explicit scope filter
GET  /api/transactions                             # all scopes only for wildcard agents
```

The agent decides the scope by reasoning about context. Emily says "I spent $87 on date night" — Rem knows that's `scope: "home"`. Emily says "Kevin paid for a haircut" — that's `scope: "salon"`.

---

## API Reference

Base URL: `http://localhost:8081`

All responses follow `{"data": ...}` or `{"data": [...], "meta": {"count": N, "total": N}}`.

All input bodies reject unknown fields (HTTP 422) so agents get a clear error instead of silently losing data.
Delete operations are soft deletes: records are marked with `deleted_at` and excluded from all standard list/get/summary queries.

HTTP error responses are normalized:

```json
{
  "error": true,
  "status": 422,
  "message": "Validation error",
  "details": [...]
}
```

---

### Health

```
GET /health → {"status": "ok"}
```

Returns `503 {"status":"unhealthy"}` if DB connectivity check fails.

---

### Entities

People, businesses, places — anything you want to reference.

#### Create

```
POST /api/entities
```

```json
{
  "scope": "salon",
  "name": "Kevin Lai",
  "type": "client",
  "phone": "444-555-6666",
  "email": "kevin@email.com",
  "notes": "Prefers appointments after 2pm",
  "tags": ["regular", "vip"],
  "meta": {"preferred_service": "haircut"}
}
```

Required: `scope`, `name`. Everything else is optional.

#### List / Search

```
GET /api/entities?scope=salon
GET /api/entities?search=kevin
GET /api/entities?search=keven            # typo-tolerant
GET /api/entities?scope=salon&search=keven+lai
GET /api/entities?type=client
GET /api/entities?tag=vip
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope |
| `search` | Fuzzy search across name, email, phone — tolerates typos, partial names, phonetic matches |
| `type` | Filter by entity type |
| `tag` | Filter by tag value |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

When `search` is provided, results include match scoring:

```json
{
  "data": [
    {"name": "Kevin Lai", "score": 0.95, "match_type": "exact", ...},
    {"name": "Kevin Smith", "score": 0.65, "match_type": "partial", ...}
  ],
  "meta": {
    "query": "keven lai",
    "confident": true,
    "best_match": "abc123"
  }
}
```

| Meta field | Description |
|------------|-------------|
| `confident` | `true` if the top result is a clear match — agent can auto-pick |
| `best_match` | Entity ID of the top result (only when `confident: true`) |

**Agent behavior:** `confident: true` → use `best_match` directly. `confident: false` → ask the user to disambiguate.

#### Activity (client profile)

```
GET /api/entities/{id}/activity
```

Returns full entity details + aggregated activity from income transactions:

```json
{
  "data": {
    "id": "abc123",
    "name": "Kevin Lai",
    "phone": "444-555-6666",
    "notes": "Prefers appointments after 2pm",
    "total_spend": 450.00,
    "visit_count": 6,
    "first_visit": "2025-08-15",
    "last_visit": "2026-02-10",
    "avg_spend": 75.00,
    "by_category": [
      {"category": "haircut", "total": 300.00, "count": 4},
      {"category": "color", "total": 150.00, "count": 2}
    ],
    "recent_transactions": [...]
  }
}
```

#### Insights (entity analytics)

```
GET /api/entities/insights?scope=salon
GET /api/entities/insights?inactive_days=30
GET /api/entities/insights?min_visits=5&sort=total_spend
GET /api/entities/insights?created_after=2026-01-01
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope |
| `inactive_days` | Only entities whose last visit was N+ days ago |
| `min_visits` | Minimum income transaction count |
| `created_after` | Entity created after date (YYYY-MM-DD) |
| `created_before` | Entity created before date |
| `sort` | `last_visit` (default), `total_spend`, `visits`, `name` |
| `limit` | Max results (default 20, max 200) |

#### Get / Update / Delete

```
GET    /api/entities/{id}
PUT    /api/entities/{id}    # partial update — only send fields to change
DELETE /api/entities/{id}
```

---

### Transactions

Income and expenses.

#### Create

```
POST /api/transactions
```

```json
{
  "scope": "salon",
  "type": "income",
  "amount": 85.00,
  "category": "haircut",
  "date": "2026-02-12",
  "description": "Kevin Lai - regular cut",
  "entity_id": "abc123",
  "payment_method": "card",
  "tags": ["walk-in"],
  "meta": {}
}
```

Required: `scope`, `type` (`income` or `expense`), `amount`, `category`, `date` (YYYY-MM-DD).

#### List

```
GET /api/transactions?scope=salon
GET /api/transactions?type=income
GET /api/transactions?category=haircut,color
GET /api/transactions?from=2026-02-01&to=2026-02-28
GET /api/transactions?entity_id=abc123
GET /api/transactions?sort=amount
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope |
| `type` | `income` or `expense` |
| `category` | Comma-separated category names |
| `entity_id` | Filter by linked entity |
| `from` | Start date (inclusive) |
| `to` | End date (inclusive) |
| `sort` | `date` (default), `created_at`, `amount` |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

#### Get / Update / Delete

```
GET    /api/transactions/{id}
PUT    /api/transactions/{id}
DELETE /api/transactions/{id}
```

---

### Items

Inventory, supplies, or any trackable thing with quantities.

#### Create

```
POST /api/items
```

```json
{
  "scope": "salon",
  "name": "Purple Shampoo 500ml",
  "category": "haircare",
  "quantity": 12,
  "unit": "bottle",
  "reorder_threshold": 5,
  "tags": ["hair-product"],
  "meta": {"supplier": "Beauty Supply Co"}
}
```

Required: `scope`, `name`. Defaults: `quantity=0`, `unit="unit"`.

#### List / Search

```
GET /api/items?scope=salon
GET /api/items?search=shampoo
GET /api/items?search=purpel+shampoo    # typo-tolerant
GET /api/items?category=haircare
```

Same fuzzy search behavior as entities — returns `score`, `match_type`, `confident`, `best_match`.

#### Low Stock

```
GET /api/items/low-stock
GET /api/items/low-stock?scope=salon
```

Returns items where `quantity <= reorder_threshold`.

#### Stock Adjustment

```
POST /api/items/{id}/adjust
```

```json
{"type": "in", "quantity": 10, "reason": "Restocked from supplier"}
{"type": "out", "quantity": 2, "reason": "Used for client"}
{"type": "adjustment", "quantity": 8, "reason": "Physical count correction"}
```

- `in` adds to current quantity
- `out` subtracts (returns 409 if insufficient stock)
- `adjustment` sets quantity to the given value

Every adjustment creates an audit trail entry in `item_movements`.

#### Movement History

```
GET /api/items/{id}/movements
```

Returns the audit trail for an item.

#### Get / Update / Delete

```
GET    /api/items/{id}
PUT    /api/items/{id}
DELETE /api/items/{id}
```

---

### Services

Fixed offerings like haircuts, treatments, or any service with a set price. Unlike items, services don't have quantities or stock — they're just a catalog of what you offer and what you charge.

#### Create

```
POST /api/services
```

```json
{
  "scope": "salon",
  "name": "Balayage",
  "category": "color",
  "price": 200.00,
  "duration_minutes": 180,
  "notes": "Includes toner and blowout",
  "tags": ["popular"],
  "meta": {}
}
```

Required: `scope`, `name`, `price`. Everything else is optional.

#### List

```
GET /api/services?scope=salon
GET /api/services?category=color
GET /api/services?tag=popular
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope |
| `category` | Filter by category |
| `tag` | Filter by tag value in `tags` JSON array |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

#### Get / Update / Delete

```
GET    /api/services/{id}
PUT    /api/services/{id}    # partial update — only send fields to change
DELETE /api/services/{id}
```

#### Example Queries

```
# "What services do we offer?"
GET /api/services?scope=salon

# "Change the price of roots to 100"
# First find the service, then update it
GET /api/services?scope=salon   # find "Roots Touch Up"
PUT /api/services/{id}          # {"price": 100.00}

# "How much do we charge for balayage?"
GET /api/services?scope=salon   # find "Balayage", read price
```

---

### Lists

Lightweight named lists — shopping lists, to-do lists, notes, reminders. The `list` field is a free-form string that acts as a category. Lists are created implicitly when the first item is added.

#### Get List Names

```
GET /api/lists
GET /api/lists?scope=home
```

Returns distinct list names with counts:

```json
{
  "data": [
    {"list": "shopping", "total": 5, "checked": 2, "unchecked": 3},
    {"list": "todo", "total": 3, "checked": 0, "unchecked": 3}
  ]
}
```

This helps the agent discover existing lists before creating new ones (avoids "shopping" vs "groceries" drift).

#### List Items

```
GET /api/lists/items?scope=home&list=shopping
GET /api/lists/items?scope=salon&list=todo&checked=false
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope |
| `list` | Filter by list name |
| `checked` | `true` or `false` — filter by checked state |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

Items are ordered by position, then creation time.

#### Add Item

```
POST /api/lists/items
```

```json
{"scope": "home", "list": "shopping", "content": "eggs"}
```

Required: `scope`, `list`, `content`. Position is auto-assigned to the end.

#### Update / Check Off

```
PUT /api/lists/items/{id}
```

```json
{"checked": true}
```

Can also update `content`, `position`, or move to a different `list`.

#### Delete Item

```
DELETE /api/lists/items/{id}
```

#### Clear List

```
DELETE /api/lists?scope=home&list=shopping                    # delete all items
DELETE /api/lists?scope=home&list=shopping&checked_only=true   # delete only checked items
```

---

### Summary

Pre-computed aggregates so agents don't burn tokens doing math. All summary endpoints accept an optional `scope` parameter.

#### Overview

```
GET /api/summary?scope=salon
GET /api/summary?period=today
GET /api/summary?period=week
GET /api/summary?period=month
GET /api/summary?period=year
GET /api/summary?period=custom&from=2026-01-01&to=2026-01-31
```

| Param | Description |
|-------|-------------|
| `scope` | Filter by scope (omit for all) |
| `period` | `today`, `week`, `month` (default), `year`, `custom` |
| `from` | Start date (required for `custom`) |
| `to` | End date (required for `custom`) |

Response:

```json
{
  "data": {
    "period": {"from": "2026-02-01", "to": "2026-02-12"},
    "income": {"total": 4250.00, "count": 47},
    "expenses": {"total": 890.00, "count": 8},
    "profit": 3360.00,
    "top_income": [
      {"category": "haircut", "total": 2100.00, "count": 28}
    ],
    "top_expenses": [
      {"category": "supplies", "total": 400.00, "count": 3}
    ],
    "clients": {
      "active": 12,
      "new": 3,
      "returning": 9
    },
    "inventory_alerts": 2
  }
}
```

#### Trends (period-over-period)

```
GET /api/summary/trends?scope=salon&period=month
```

Compares current period to the previous period of the same length:

```json
{
  "data": {
    "current": {"income": 4250.00, "expenses": 890.00, "profit": 3360.00},
    "previous": {"income": 3800.00, "expenses": 920.00, "profit": 2880.00},
    "change": {
      "income": {"amount": 450.00, "percent": 11.8},
      "expenses": {"amount": -30.00, "percent": -3.3},
      "profit": {"amount": 480.00, "percent": 16.7}
    },
    "trend": "up"
  }
}
```

`trend` is `"up"` (>5%), `"down"` (<-5%), or `"stable"`.

#### By Day of Week

```
GET /api/summary/by-day?scope=salon&period=month
```

Income breakdown by day of week:

```json
{
  "data": {
    "days": [
      {"day": "Monday", "total": 850.00, "count": 8},
      {"day": "Tuesday", "total": 620.00, "count": 6},
      ...
    ],
    "busiest": "Saturday"
  }
}
```

#### By Scope

```
GET /api/summary/by-scope?period=month
GET /api/summary/by-scope?scope=salon&period=custom&from=2026-02-01&to=2026-02-29
```

Returns income/expense/profit grouped by scope for the selected period.

---

## Design Principles

### Agent-first
Responses are optimized for LLM consumption. Pre-computed aggregates, confidence signals, compact JSON. The API does the math so the agent doesn't waste tokens on arithmetic.

### Fuzzy search with confidence signals
Search tolerates typos ("keven" → "Kevin"), partial names, and phonetic matches (Soundex). Results include `score`, `match_type`, `confident`, and `best_match` so the agent knows whether to auto-pick or ask the user.

### Strict input validation
All input schemas reject unknown fields (`extra: "forbid"`). If an agent sends `{"name": "Kevin", "phon": "555-1234"}`, it gets a 422 error pointing to the bad field — not a silent success that drops the phone number.

### Scope-based namespacing
One API instance serves multiple contexts. A salon owner who also tracks home expenses uses `scope: "salon"` and `scope: "home"`. Scoped indexes keep queries fast. Cross-scope reads are controlled by token scope permissions.

---

## Case Studies: Emily + Rem

Emily owns a small hair salon. Her LLM assistant **Rem** uses the Kei API to manage both her salon operations and personal life.

### Salon: Client walks in

> **Emily:** "Kevin's here for his appointment"

```
Rem: GET /api/entities?scope=salon&search=kevin
  → confident: true, best_match: "abc123"
Rem: GET /api/entities/abc123/activity
  → Kevin Lai, 6 visits, avg spend $75, prefers appointments after 2pm,
    last visit 3 weeks ago, usually gets haircut
Rem: "Kevin Lai is here! He's been coming for 6 visits, usually gets a
     haircut ($75 avg). His last visit was 3 weeks ago. He prefers
     afternoon appointments. Notes say he likes the organic dye."
```

### Salon: Recording a payment

> **Emily:** "Kevin just paid 85 for his haircut, cash"

```
Rem: POST /api/transactions
  {scope: "salon", type: "income", amount: 85, category: "haircut",
   date: "2026-02-13", entity_id: "abc123", payment_method: "cash"}
  → Transaction created
Rem: "Got it! Recorded $85 cash payment from Kevin for a haircut."
```

### Salon: Fixing a mistake

> **Emily:** "No wait, I meant $58 not $85"

```
Rem: PUT /api/transactions/{txn_id}
  {amount: 58}
  → Updated
Rem: "Fixed — updated to $58."
```

### Salon: Ambiguous client name

> **Emily:** "Update Keven's phone number to 555-9999"

```
Rem: GET /api/entities?scope=salon&search=keven
  → confident: false (Kevin Lai: 0.72, Kevin Smith: 0.68)
Rem: "I found two Kevins — Kevin Lai and Kevin Smith. Which one?"
Emily: "Lai"
Rem: PUT /api/entities/{kevin_lai_id}
  {phone: "555-9999"}
Rem: "Updated Kevin Lai's phone to 555-9999."
```

### Salon: Inventory check

> **Emily:** "Are we running low on anything?"

```
Rem: GET /api/items/low-stock?scope=salon
  → Purple Shampoo: 3 bottles (threshold: 5), Foil Sheets: 10 (threshold: 15)
Rem: "Two items are low:
     - Purple Shampoo: 3 bottles left (reorder at 5)
     - Foil Sheets: 10 left (reorder at 15)
     Want me to add these to the salon shopping list?"
Emily: "Yes"
Rem: POST /api/lists/items {scope: "salon", list: "shopping", content: "Purple Shampoo (need 12)"}
Rem: POST /api/lists/items {scope: "salon", list: "shopping", content: "Foil Sheets (need 20)"}
```

### Salon: Business performance

> **Emily:** "How's the salon doing this month compared to last?"

```
Rem: GET /api/summary/trends?scope=salon&period=month
  → current: income $4,250, expenses $890, profit $3,360
    previous: income $3,800, expenses $920, profit $2,880
    change: income +11.8%, profit +16.7%, trend: "up"
Rem: "Great month! Income is up 11.8% to $4,250 and profit jumped 16.7%
     to $3,360. You also spent slightly less on expenses ($890 vs $920).
     12 active clients this month, 3 of them are new."
```

### Salon: Busiest days

> **Emily:** "What's my busiest day?"

```
Rem: GET /api/summary/by-day?scope=salon&period=month
  → busiest: "Saturday", Saturday total: $1,200
Rem: "Saturday is your busiest day — $1,200 in income this month.
     Friday is second at $850. Mondays are the slowest."
```

### Salon: Inactive clients

> **Emily:** "Who haven't I seen in a while?"

```
Rem: GET /api/entities/insights?scope=salon&inactive_days=30&sort=last_visit
  → Sarah Chen: last visit 45 days ago, 3 visits, $210 total
    Mike Jones: last visit 60 days ago, 2 visits, $150 total
Rem: "Two clients haven't visited in over a month:
     - Sarah Chen: last here 45 days ago (3 visits, $210 total)
     - Mike Jones: last here 60 days ago (2 visits, $150)
     Want me to note anything for follow-up?"
```

### Home: Personal expense

> **Emily:** "Rem, date night last night cost us 87 bucks at that Italian place"

```
Rem: POST /api/transactions
  {scope: "home", type: "expense", amount: 87, category: "dining",
   date: "2026-02-12", description: "Italian restaurant - date night"}
Rem: "Logged $87 for date night dining."
```

### Home: Shopping list

> **Emily:** "Add eggs and milk to the shopping list"

```
Rem: POST /api/lists/items {scope: "home", list: "shopping", content: "eggs"}
Rem: POST /api/lists/items {scope: "home", list: "shopping", content: "milk"}
Rem: "Added eggs and milk to your shopping list."
```

### Home: Checking the list

> **Emily:** "What's on my shopping list?"

```
Rem: GET /api/lists/items?scope=home&list=shopping&checked=false
  → eggs, milk, bread, dish soap
Rem: "Your shopping list has 4 items: eggs, milk, bread, and dish soap."
```

### Home: After shopping

> **Emily:** "Got the eggs and milk"

```
Rem: PUT /api/lists/items/{eggs_id} {checked: true}
Rem: PUT /api/lists/items/{milk_id} {checked: true}
Rem: "Checked off eggs and milk. Bread and dish soap are still on the list."
```

### Cross-scope: Overall picture

> **Emily:** "How much did I spend total this month, everything?"

```
Rem: GET /api/summary?period=month
  → (no scope filter — returns all)
  income: $4,250, expenses: $1,200, profit: $3,050
Rem: "Across everything this month: $4,250 income (all from the salon),
     $1,200 in expenses ($890 salon + $310 personal), net $3,050."
```

### Salon: Task management

> **Emily:** "Rem, remind me to call the landlord about the lease"

```
Rem: POST /api/lists/items
  {scope: "salon", list: "todo", content: "Call landlord about lease renewal"}
Rem: "Added to your salon to-do list."
```

> **Emily:** "What do I need to do for the salon?"

```
Rem: GET /api/lists/items?scope=salon&list=todo&checked=false
  → Call landlord about lease renewal, Order new chairs, Update website hours
Rem: "Your salon to-do list:
     1. Call landlord about lease renewal
     2. Order new chairs
     3. Update website hours"
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI |
| Database | SQLite (WAL mode) |
| ORM | SQLAlchemy 2.x |
| Validation | Pydantic 2.x |
| Search | rapidfuzz (fuzzy matching) + Soundex (phonetic) |
| Auth | Bearer token |
| Deployment | Docker or bare metal |
