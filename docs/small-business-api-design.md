# Kei API (経) — Design Document

*Agent-first small business API*

**Status:** Draft  
**Author:** Beatrice  
**Date:** 2026-02-10  
**Executor:** Ram  

---

## Overview

A lightweight, agent-first API for small business operations. Designed for LLM personal assistants (like Rem) to efficiently manage income, expenses, inventory, and customers with minimal token overhead.

### Goals

1. **Agent-first design** — Responses optimized for LLM consumption, not human UIs
2. **Token efficiency** — Compact JSON, summary endpoints, no verbose formatting
3. **Simple CRUD** — Predictable REST patterns, typed schemas
4. **Expandable** — Clean foundation for productization (multi-tenant, white-label)
5. **Emily-friendly** — Optional dashboard UI for at-a-glance views

### Non-Goals (MVP)

- Full double-entry accounting
- Payroll/tax calculations
- Multi-currency
- Real-time sync with banks

---

## Tech Stack

Matches emilia-webapp for consistency:

| Layer | Technology |
|-------|------------|
| Framework | FastAPI |
| Database | SQLite (single file, easy backup) |
| ORM | SQLAlchemy 2.x + Pydantic |
| Auth | Bearer token (simple, like emilia-webapp) |
| Deployment | Docker container or bare metal |

**File structure:**
```
kei-api/
├── main.py
├── config.py
├── dependencies.py
├── db/
│   ├── connection.py
│   ├── models.py          # SQLAlchemy models
│   └── repositories/
│       ├── transactions.py
│       ├── clients.py
│       ├── inventory.py
│       └── reports.py
├── routers/
│   ├── transactions.py
│   ├── clients.py
│   ├── inventory.py
│   └── dashboard.py
├── schemas/
│   ├── requests.py
│   ├── responses.py
│   └── enums.py
├── services/
│   └── analytics.py
└── data/
    └── business.db
```

---

## Database Schema

### Core Tables

```sql
-- Transactions: income and expenses
CREATE TABLE transactions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'CAD',
    category TEXT NOT NULL,
    description TEXT,
    date TEXT NOT NULL,  -- ISO 8601: YYYY-MM-DD
    client_id TEXT REFERENCES clients(id),
    tags TEXT,  -- JSON array for flexible tagging
    payment_method TEXT,  -- cash, card, etransfer, etc.
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Clients/Customers
CREATE TABLE clients (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    notes TEXT,
    tags TEXT,  -- JSON array: ["vip", "monthly-regular"]
    first_visit TEXT,  -- ISO date
    last_visit TEXT,   -- ISO date (auto-updated)
    visit_count INTEGER DEFAULT 0,
    total_spend REAL DEFAULT 0,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Inventory (products, supplies)
CREATE TABLE inventory (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    sku TEXT UNIQUE,
    category TEXT,
    quantity REAL DEFAULT 0,
    unit TEXT DEFAULT 'unit',  -- unit, ml, g, etc.
    cost_per_unit REAL,
    sell_price REAL,
    reorder_threshold REAL,
    supplier TEXT,
    notes TEXT,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Inventory movements (stock in/out log)
CREATE TABLE inventory_movements (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    inventory_id TEXT NOT NULL REFERENCES inventory(id),
    type TEXT NOT NULL CHECK (type IN ('in', 'out', 'adjustment')),
    quantity REAL NOT NULL,
    reason TEXT,  -- purchase, sale, damaged, correction
    transaction_id TEXT REFERENCES transactions(id),
    created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Categories (configurable)
CREATE TABLE categories (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'inventory')),
    name TEXT NOT NULL,
    icon TEXT,
    color TEXT,
    sort_order INTEGER DEFAULT 0
);

-- Indexes for common queries
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_category ON transactions(category);
CREATE INDEX idx_clients_last_visit ON clients(last_visit);
CREATE INDEX idx_inventory_quantity ON inventory(quantity);
```

### Default Categories (Salon)

```sql
-- Income categories
INSERT INTO categories VALUES ('haircut', 'income', 'Haircut', '✂️', '#4CAF50', 1);
INSERT INTO categories VALUES ('color', 'income', 'Color/Dye', '🎨', '#9C27B0', 2);
INSERT INTO categories VALUES ('treatment', 'income', 'Treatment', '💆', '#2196F3', 3);
INSERT INTO categories VALUES ('product-sale', 'income', 'Product Sale', '🛍️', '#FF9800', 4);
INSERT INTO categories VALUES ('tip', 'income', 'Tip', '💝', '#E91E63', 5);
INSERT INTO categories VALUES ('other-income', 'income', 'Other', '💰', '#607D8B', 99);

-- Expense categories
INSERT INTO categories VALUES ('supplies', 'expense', 'Supplies', '📦', '#795548', 1);
INSERT INTO categories VALUES ('rent', 'expense', 'Rent', '🏠', '#F44336', 2);
INSERT INTO categories VALUES ('utilities', 'expense', 'Utilities', '💡', '#FFC107', 3);
INSERT INTO categories VALUES ('marketing', 'expense', 'Marketing', '📢', '#00BCD4', 4);
INSERT INTO categories VALUES ('equipment', 'expense', 'Equipment', '🔧', '#9E9E9E', 5);
INSERT INTO categories VALUES ('other-expense', 'expense', 'Other', '📋', '#607D8B', 99);
```

---

## API Design — Agent-First Principles

### Design Rules

1. **Compact responses** — No nested nulls, no verbose metadata
2. **Summary endpoints** — Pre-computed aggregates, don't make agents do math
3. **Flexible filters** — Date ranges, categories via query params
4. **Bulk operations** — Insert multiple records in one call
5. **Idempotent** — Safe retries, use client-provided IDs when sensible

### Response Format

All responses follow:
```json
{
  "data": { ... },      // or array
  "meta": {             // optional, only when useful
    "count": 10,
    "period": "2026-02"
  }
}
```

Error responses:
```json
{
  "error": "not_found",
  "message": "Client not found",
  "detail": "No client with id 'abc123'"
}
```

---

## API Endpoints

### Transactions

```
POST   /api/transactions              # Create one or bulk
GET    /api/transactions              # List with filters
GET    /api/transactions/:id          # Get single
PUT    /api/transactions/:id          # Update
DELETE /api/transactions/:id          # Delete
```

**POST /api/transactions** — Create transaction(s)
```json
// Single
{
  "type": "income",
  "amount": 85.00,
  "category": "haircut",
  "date": "2026-02-10",
  "client_id": "abc123",
  "description": "Cut + style",
  "payment_method": "card"
}

// Bulk (array)
[
  { "type": "income", "amount": 85, "category": "haircut", "date": "2026-02-10" },
  { "type": "income", "amount": 15, "category": "tip", "date": "2026-02-10" }
]
```

Response:
```json
{
  "data": { "id": "tx_xxx", "type": "income", "amount": 85.00, ... },
  "meta": { "created": 1 }
}
```

**GET /api/transactions** — List with filters
```
?type=income|expense
?category=haircut,color
?from=2026-02-01
?to=2026-02-28
?client_id=abc123
?limit=50
?offset=0
```

Response (agent-optimized):
```json
{
  "data": [
    { "id": "tx_1", "type": "income", "amount": 85, "category": "haircut", "date": "2026-02-10", "description": "Cut + style" },
    { "id": "tx_2", "type": "income", "amount": 15, "category": "tip", "date": "2026-02-10" }
  ],
  "meta": { "count": 2, "total": 2 }
}
```

---

### Clients

```
POST   /api/clients                   # Create
GET    /api/clients                   # List
GET    /api/clients/:id               # Get with visit history
PUT    /api/clients/:id               # Update
DELETE /api/clients/:id               # Soft delete / archive
GET    /api/clients/:id/transactions  # Client's transaction history
```

**GET /api/clients/:id** — Full client profile
```json
{
  "data": {
    "id": "abc123",
    "name": "Jane Doe",
    "phone": "+1604...",
    "email": "jane@email.com",
    "tags": ["regular", "color-specialist"],
    "first_visit": "2025-06-15",
    "last_visit": "2026-02-08",
    "visit_count": 12,
    "total_spend": 1450.00,
    "notes": "Prefers appointments after 2pm"
  }
}
```

**GET /api/clients** — List with search
```
?search=jane           # name, email, phone
?tag=regular
?inactive_days=90      # hasn't visited in X days
?sort=last_visit|total_spend|name
?limit=20
```

---

### Inventory

```
POST   /api/inventory                 # Add item
GET    /api/inventory                 # List
GET    /api/inventory/:id             # Get with movement history
PUT    /api/inventory/:id             # Update
DELETE /api/inventory/:id             # Archive
POST   /api/inventory/:id/adjust      # Stock adjustment
GET    /api/inventory/low-stock       # Items below reorder threshold
```

**POST /api/inventory/:id/adjust** — Stock movement
```json
{
  "type": "out",
  "quantity": 2,
  "reason": "sale",
  "transaction_id": "tx_xxx"  // optional: link to sale
}
```

**GET /api/inventory/low-stock** — Reorder alerts
```json
{
  "data": [
    { "id": "inv_1", "name": "Purple Shampoo 500ml", "quantity": 2, "reorder_threshold": 5, "supplier": "Beauty Supply Co" },
    { "id": "inv_2", "name": "Foil Sheets", "quantity": 50, "reorder_threshold": 100 }
  ],
  "meta": { "count": 2 }
}
```

---

### Dashboard / Reports — The Token-Saver Endpoints

These are the star of the show. Pre-computed summaries so agents don't burn tokens aggregating.

```
GET /api/dashboard/summary            # The "at a glance" view
GET /api/dashboard/trends             # Period-over-period comparison
GET /api/dashboard/top-categories     # Revenue by category
GET /api/dashboard/client-insights    # Client metrics
```

**GET /api/dashboard/summary** — Daily agent check-in
```
?period=today|week|month|year|custom
?from=2026-02-01
?to=2026-02-10
```

Response:
```json
{
  "data": {
    "period": { "from": "2026-02-01", "to": "2026-02-10" },
    "income": {
      "total": 4250.00,
      "count": 47,
      "average": 90.43
    },
    "expenses": {
      "total": 890.00,
      "count": 8
    },
    "profit": 3360.00,
    "margin_percent": 79.1,
    "clients": {
      "active": 31,
      "new": 5,
      "returning": 26
    },
    "top_category": { "name": "haircut", "amount": 2100.00 },
    "inventory_alerts": 2
  }
}
```

**GET /api/dashboard/trends** — Comparison
```
?period=month
?compare=previous  # vs last month
```

Response:
```json
{
  "data": {
    "current": { "period": "2026-02", "income": 4250, "expenses": 890, "profit": 3360 },
    "previous": { "period": "2026-01", "income": 3800, "expenses": 920, "profit": 2880 },
    "change": {
      "income": { "amount": 450, "percent": 11.8 },
      "expenses": { "amount": -30, "percent": -3.3 },
      "profit": { "amount": 480, "percent": 16.7 }
    },
    "trend": "up"  # up, down, stable
  }
}
```

**GET /api/dashboard/top-categories**
```
?period=month&type=income&limit=5
```

Response:
```json
{
  "data": [
    { "category": "haircut", "amount": 2100, "percent": 49.4, "count": 28 },
    { "category": "color", "amount": 1400, "percent": 32.9, "count": 10 },
    { "category": "tip", "amount": 350, "percent": 8.2, "count": 35 },
    { "category": "treatment", "amount": 280, "percent": 6.6, "count": 4 },
    { "category": "product-sale", "amount": 120, "percent": 2.8, "count": 6 }
  ]
}
```

**GET /api/dashboard/client-insights**
```json
{
  "data": {
    "total_clients": 89,
    "active_this_month": 31,
    "new_this_month": 5,
    "at_risk": 12,  # no visit in 60+ days
    "top_spenders": [
      { "id": "c1", "name": "Jane D.", "total_spend": 890, "visits": 8 },
      { "id": "c2", "name": "Sarah M.", "total_spend": 720, "visits": 6 }
    ],
    "avg_visit_value": 92.50,
    "avg_visits_per_client": 3.2
  }
}
```

---

## Agent Integration Examples

### Rem's Daily Summary (Token-Efficient)

```python
# One API call, ~200 tokens response
GET /api/dashboard/summary?period=today

# Rem formats:
"Today's salon summary: $425 income from 5 clients (4 returning, 1 new). 
Expenses: $45 on supplies. Profit: $380. No inventory alerts."
```

### Recording a Transaction (Rem after Emily reports)

```python
POST /api/transactions
{
  "type": "income",
  "amount": 95,
  "category": "haircut",
  "date": "2026-02-10",
  "description": "Sarah - cut + blowout",
  "payment_method": "card"
}
```

### Weekly Report for Emily

```python
GET /api/dashboard/summary?period=week
GET /api/dashboard/top-categories?period=week&type=income
GET /api/dashboard/client-insights

# Rem compiles into conversational WhatsApp message
```

### Low Stock Alert (Rem proactive)

```python
GET /api/inventory/low-stock

# If items returned:
"Emily-sama~ Heads up: Purple Shampoo (2 left) and Foil Sheets (50 left) 
are running low. Want me to add them to the shopping list? 💙"
```

---

## MVP Scope

### Phase 1 — Core (Week 1)
- [ ] Project setup (FastAPI, SQLite, Docker)
- [ ] Transaction CRUD
- [ ] Basic dashboard summary endpoint
- [ ] Auth (bearer token)
- [ ] Seed data + default categories

### Phase 2 — Clients & Inventory (Week 2)
- [ ] Client CRUD + search
- [ ] Inventory CRUD + adjustments
- [ ] Low-stock endpoint
- [ ] Client insights endpoint

### Phase 3 — Polish (Week 3)
- [ ] Trends/comparison endpoint
- [ ] Bulk transaction import
- [ ] Simple web dashboard (optional, for Emily)
- [ ] Sheets sync (optional, one-way export)

---

## Future Expansion (Post-MVP)

- **Multi-tenant** — business_id on all tables, separate auth
- **Appointments integration** — Link to Google Calendar
- **Invoicing** — Generate PDF invoices
- **Reports export** — CSV/PDF for accountant
- **Mobile app** — React Native or PWA
- **Productization** — White-label SaaS for salons/small biz

---

## Decisions

1. **Standalone service** — separate repo, same Docker network as emilia-webapp
2. **Full switch** — no Sheets sync; API becomes source of truth when ready
3. **Name: `kei-api`** (経 = business/manage) — Port 8081

---

## Summary

**Kei** (経) — a FastAPI + SQLite service with agent-first endpoints. Rem gets token-efficient summaries, Emily gets a clean dashboard, and the foundation supports future expansion into a productized small business tool.

**Repo:** `kei-api` (standalone, `/home/tbach/Projects/emilia-project/kei-api/`)  
**Port:** 8081  
**Ram's deliverable:** Working API with transaction CRUD + dashboard summary in ~2 days.

---

*Document drafted by Beatrice. Decisions finalized 2026-02-10. Ready for Ram.*
