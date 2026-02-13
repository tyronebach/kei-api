# Kei API (経)

Agent-first data API. Three tables, CRUD endpoints, one summary endpoint. Designed for LLM assistants to store and retrieve data via simple HTTP calls.

Domain-agnostic — works for salon management, household tracking, small business ops, whatever. The `meta` JSON field on every table handles domain-specific data without schema changes.

## Setup

```bash
# Local dev
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # edit KEI_API_TOKEN
.venv/bin/uvicorn main:app --port 8081 --reload

# Docker
docker build -t kei-api .
docker run -p 8081:8081 -e KEI_API_TOKEN=your-secret -v kei-data:/app/data kei-api
```

## Auth

All `/api/*` endpoints require a bearer token:

```
Authorization: Bearer <KEI_API_TOKEN>
```

The `/health` endpoint is public.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `KEI_API_TOKEN` | `changeme` | Bearer token for API auth |
| `KEI_DATABASE_URL` | `sqlite:///./data/kei.db` | SQLite database path |

---

## API Reference

Base URL: `http://localhost:8081`

All responses follow `{"data": ...}` or `{"data": [...], "meta": {"count": N, "total": N}}`.

---

### Health

```
GET /health
```

```json
{"status": "ok"}
```

---

### Entities

People, businesses, places — anything you want to reference.

#### Create

```
POST /api/entities
```

```json
{
  "name": "Kevin",
  "type": "client",
  "phone": "444-555-6666",
  "email": "kevin@email.com",
  "notes": "Prefers appointments after 2pm",
  "tags": ["regular", "vip"],
  "meta": {"preferred_service": "haircut"}
}
```

Required: `name`. Everything else is optional.

#### List

```
GET /api/entities
GET /api/entities?search=kevin
GET /api/entities?type=client
GET /api/entities?tag=vip
GET /api/entities?limit=20&offset=0
```

| Param | Description |
|-------|-------------|
| `search` | Searches name, email, phone (case-insensitive) |
| `type` | Filter by entity type |
| `tag` | Filter by tag value |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

#### Get / Update / Delete

```
GET    /api/entities/{id}
PUT    /api/entities/{id}    # partial update, only send fields to change
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
  "type": "expense",
  "amount": 22.00,
  "category": "groceries",
  "date": "2026-02-12",
  "description": "Costco - bought meat",
  "entity_id": "abc123",
  "payment_method": "card",
  "tags": ["food"],
  "meta": {"store": "costco"}
}
```

Required: `type` (`income` or `expense`), `amount`, `category`, `date` (YYYY-MM-DD).

#### List

```
GET /api/transactions
GET /api/transactions?type=income
GET /api/transactions?category=haircut,groceries
GET /api/transactions?from=2026-02-01&to=2026-02-28
GET /api/transactions?entity_id=abc123
```

| Param | Description |
|-------|-------------|
| `type` | `income` or `expense` |
| `category` | Comma-separated category names |
| `entity_id` | Filter by linked entity |
| `from` | Start date (inclusive) |
| `to` | End date (inclusive) |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

Results ordered by date descending.

#### Get / Update / Delete

```
GET    /api/transactions/{id}
PUT    /api/transactions/{id}
DELETE /api/transactions/{id}
```

---

### Items

Inventory, supplies, or any trackable thing.

#### Create

```
POST /api/items
```

```json
{
  "name": "Purple Shampoo 500ml",
  "category": "supplies",
  "quantity": 12,
  "unit": "bottle",
  "notes": "Reorder at 5",
  "tags": ["hair-product"],
  "meta": {"supplier": "Beauty Supply Co", "reorder_threshold": 5}
}
```

Required: `name`. Defaults: `quantity=0`, `unit="unit"`.

#### List

```
GET /api/items
GET /api/items?search=shampoo
GET /api/items?category=supplies
```

| Param | Description |
|-------|-------------|
| `search` | Search by name (case-insensitive) |
| `category` | Filter by category |
| `limit` | Max results (default 50, max 200) |
| `offset` | Pagination offset |

#### Get / Update / Delete

```
GET    /api/items/{id}
PUT    /api/items/{id}
DELETE /api/items/{id}
```

---

### Summary

Pre-computed aggregates so agents don't burn tokens doing math.

```
GET /api/summary
GET /api/summary?period=today
GET /api/summary?period=week
GET /api/summary?period=month
GET /api/summary?period=year
GET /api/summary?period=custom&from=2026-01-01&to=2026-01-31
```

| Param | Description |
|-------|-------------|
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
    "top_categories": [
      {"category": "haircut", "total": 2100.00, "count": 28},
      {"category": "color", "total": 1400.00, "count": 10}
    ]
  }
}
```

---

## Agent Usage Examples

**Voice: "hey Rem I spent 22 at costco today, bought meat"**

```
POST /api/transactions
{"type": "expense", "amount": 22, "category": "groceries", "date": "2026-02-12", "description": "bought meat", "meta": {"store": "costco"}}
```

**Voice: "hey Rem update my client Kevin, his phone number is 444x"**

```
GET /api/entities?search=kevin
PUT /api/entities/{id}
{"phone": "444x"}
```

**Voice: "hey Rem how's the salon doing this month?"**

```
GET /api/summary?period=month
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI |
| Database | SQLite (WAL mode) |
| ORM | SQLAlchemy 2.x |
| Validation | Pydantic 2.x |
| Auth | Bearer token |
| Deployment | Docker or bare metal |
