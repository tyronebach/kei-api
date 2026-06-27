# Kei Dashboard — Implementation Plan

**Goal:** Financial dashboard frontend for Kei API — household snapshot viewer, spending trends, scope filtering. Served behind home Caddy proxy.

**Architecture:** Vite + React + TypeScript + Tailwind + TanStack Query. No backend — talks directly to Kei API (localhost:8081). PIN-gated entry (env var). Snapshots stored as a new Kei API table, piped from Tributary. Charts via Recharts.

**Tech Stack:** Vite, React 19, TypeScript, Tailwind CSS 4, TanStack Query v5, TanStack Router, Recharts, date-fns

---

## Part A: Kei API — Snapshots Endpoint + CORS + PIN Auth

### Task A1: Snapshot DB Model + Migration

**Files:**
- Modify: `db/models.py` — add `Snapshot` model
- Create: `alembic/versions/f1a2b3c4d5e6_add_snapshots_table.py` — migration
- Modify: `config.py` — add `valid_scopes` to include "household"

**Model:**
```python
class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("scope", "date", name="uq_snapshots_scope_date"),
        Index("idx_snapshots_scope", "scope"),
        Index("idx_snapshots_date", "date"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    scope: Mapped[str] = mapped_column(String, nullable=False)  # "household"
    date: Mapped[str] = mapped_column(String, nullable=False)   # YYYY-MM-DD
    data: Mapped[dict] = mapped_column(JSON, nullable=False)    # full snapshot blob
    created_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
```

Steps:
- [ ] Add Snapshot model to `db/models.py`
- [ ] Generate migration: `alembic revision --autogenerate -m "add_snapshots_table"`
- [ ] Run migration: `alembic upgrade head`
- [ ] Verify table exists
- [ ] Commit: `feat: add snapshots table`

### Task A2: Snapshots Router

**Files:**
- Create: `routers/snapshots.py`
- Modify: `main.py` — register router
- Create: `schemas.py` additions — `SnapshotCreate`, `SnapshotOut`

**Endpoints:**
- `GET /api/snapshots` — list snapshots, query params: `scope`, `from`, `to`, `limit`, `offset`
- `GET /api/snapshots/latest` — latest snapshot for scope
- `GET /api/snapshots/{snapshot_id}` — single snapshot
- `POST /api/snapshots` — upsert by (scope, date). If exists for that date+scope, replace data.

Steps:
- [ ] Add `SnapshotCreate` and `SnapshotOut` to `schemas.py`
- [ ] Create `routers/snapshots.py` with all 4 endpoints
- [ ] Register in `main.py`
- [ ] Test via curl: POST a snapshot, GET it back, GET /latest
- [ ] Commit: `feat: add snapshots API`

### Task A3: Backfill Existing Snapshots

**Files:**
- Create: `scripts/backfill_snapshots.py` — reads JSON files from `~/clawd-agents/household/financial_snapshots/*.json`, POSTs each to Kei API

Steps:
- [ ] Write backfill script
- [ ] Run it, verify all 10 snapshots loaded
- [ ] Verify `GET /api/snapshots?scope=household` returns them in date order
- [ ] Commit: `feat: add snapshot backfill script`

### Task A4: CORS Configuration

**Files:**
- Modify: `.env` — add dashboard origin to `KEI_CORS_ORIGINS`

Steps:
- [ ] Add `KEI_CORS_ORIGINS=["http://localhost:5173","https://kei.binktogether.com"]` to `.env`
- [ ] Restart Kei API, verify CORS headers present
- [ ] Commit: `feat: configure CORS for dashboard`

---

## Part B: Frontend — Kei Dashboard

### Task B1: Project Scaffold

**Files:**
- Create: `~/Projects/kei-dashboard/` — full Vite project

Steps:
- [ ] `npm create vite@latest kei-dashboard -- --template react-ts`
- [ ] `cd kei-dashboard && npm install`
- [ ] Install deps: `npm install @tanstack/react-query @tanstack/react-router recharts tailwindcss @tailwindcss/vite date-fns`
- [ ] Configure Tailwind (CSS import)
- [ ] Configure Vite dev proxy to `localhost:8081`
- [ ] Create `.env` with `VITE_KEI_API_URL=http://localhost:8081` and `VITE_PIN=1234`
- [ ] Verify dev server runs
- [ ] Commit: `feat: scaffold kei-dashboard`

### Task B2: API Client + Auth

**Files:**
- Create: `src/lib/api.ts` — fetch wrapper with Bearer token
- Create: `src/lib/auth.ts` — PIN gate logic (localStorage + env check)
- Create: `src/components/PinGate.tsx` — PIN entry screen

**Auth flow:**
1. On load, check `localStorage.getItem("kei-pin")`
2. If missing or wrong, show PIN pad
3. PIN is compared client-side against `VITE_PIN` env var
4. On match, store in localStorage, proceed
5. Kei API token stored in env var, used in all API calls

Steps:
- [ ] Create `src/lib/api.ts` — typed fetch with auth header, base URL from env
- [ ] Create `src/lib/auth.ts` — `isAuthenticated()`, `authenticate(pin)`, `logout()`
- [ ] Create `src/components/PinGate.tsx` — minimal numeric PIN entry UI
- [ ] Verify PIN gate blocks access, stores on success
- [ ] Commit: `feat: API client + PIN auth gate`

### Task B3: Layout + Router

**Files:**
- Create: `src/routes/` — TanStack Router file-based routes
- Create: `src/components/Layout.tsx` — shell with sidebar nav
- Create: `src/components/Sidebar.tsx` — nav links + scope filter

**Routes:**
- `/` — Dashboard (snapshot overview + key metrics)
- `/spending` — Spending breakdown (transactions by category, scope)
- `/trends` — Trend charts (snapshot-over-time, month-over-month)
- `/transactions` — Transaction list with filters

**Sidebar:**
- Scope selector: All | Home | Salon | Woodwards | Synthhub
- Period selector: This Week | This Month | Custom Range
- Nav links to each route

Steps:
- [ ] Set up TanStack Router with route tree
- [ ] Create Layout shell with sidebar
- [ ] Create Sidebar with scope/period selectors (stored in URL search params)
- [ ] Verify navigation works between routes
- [ ] Commit: `feat: layout + router + sidebar`

### Task B4: Dashboard Page (Home)

**Files:**
- Create: `src/routes/index.tsx`
- Create: `src/components/NetWorthCard.tsx`
- Create: `src/components/AccountsGrid.tsx`
- Create: `src/components/SpendingSummaryCard.tsx`
- Create: `src/hooks/useSnapshots.ts`
- Create: `src/hooks/useSummary.ts`

**What it shows:**
- Net worth headline (from latest snapshot)
- Liquid accounts grid
- Credit cards + LOC balances
- Investment portfolio total + breakdown
- Current period income/expense/profit summary (from `/api/summary`)
- Net worth mini sparkline (from snapshot history)

Steps:
- [ ] Create `useSnapshots` hook — fetches `/api/snapshots/latest` + `/api/snapshots?from=...&to=...`
- [ ] Create `useSummary` hook — fetches `/api/summary` with scope/period params
- [ ] Build `NetWorthCard` — big number + sparkline trend
- [ ] Build `AccountsGrid` — liquid + credit + LOC in card grid
- [ ] Build `SpendingSummaryCard` — income/expense/profit bars
- [ ] Compose into dashboard page
- [ ] Verify with real data
- [ ] Commit: `feat: dashboard home page`

### Task B5: Spending Page

**Files:**
- Create: `src/routes/spending.tsx`
- Create: `src/components/CategoryBreakdown.tsx`
- Create: `src/components/ScopeBreakdown.tsx`
- Create: `src/hooks/useTransactions.ts`

**What it shows:**
- Spending by category (pie/donut chart + table) from `/api/summary`
- Spending by scope from `/api/summary/by-scope`
- Top transactions list
- Filterable by scope + period

Steps:
- [ ] Create `useTransactions` hook — fetches `/api/transactions` with filters
- [ ] Build `CategoryBreakdown` — donut chart + category list with amounts
- [ ] Build `ScopeBreakdown` — bar chart comparing scopes
- [ ] Compose spending page with filters from sidebar context
- [ ] Verify with real data
- [ ] Commit: `feat: spending page`

### Task B6: Trends Page

**Files:**
- Create: `src/routes/trends.tsx`
- Create: `src/components/NetWorthChart.tsx`
- Create: `src/components/MonthlyChart.tsx`
- Create: `src/components/InvestmentChart.tsx`

**What it shows:**
- Net worth over time (line chart from snapshots)
- Monthly income vs expenses (bar chart from `/api/summary/by-month`)
- Investment portfolio value over time (line from snapshots)
- Month-over-month change indicators

Steps:
- [ ] Build `NetWorthChart` — line chart, x=date, y=net_worth from snapshots
- [ ] Build `MonthlyChart` — grouped bar, income vs expense per month
- [ ] Build `InvestmentChart` — stacked area, investment accounts over time
- [ ] Compose trends page
- [ ] Verify with real (thin) data
- [ ] Commit: `feat: trends page`

### Task B7: Transactions Page

**Files:**
- Create: `src/routes/transactions.tsx`
- Create: `src/components/TransactionTable.tsx`
- Create: `src/components/TransactionFilters.tsx`

**What it shows:**
- Paginated transaction table
- Filters: scope, category, type (income/expense), date range, search
- Sortable columns

Steps:
- [ ] Build `TransactionFilters` — filter bar synced to URL search params
- [ ] Build `TransactionTable` — paginated table with scope/category/amount/date/description
- [ ] Wire up pagination (offset/limit to API)
- [ ] Verify filters work
- [ ] Commit: `feat: transactions page`

---

## Part C: Deployment

### Task C1: Build + Caddy Config

**Files:**
- Modify: Caddy config (via home-proxy skill) — add `kei.binktogether.com`
- Create: `~/Projects/kei-dashboard/.env.production`

Steps:
- [ ] Create production env: `VITE_KEI_API_URL=https://kei-api.binktogether.com` (or local proxy path)
- [ ] `npm run build` — verify clean build
- [ ] Add Caddy site block serving `~/Projects/kei-dashboard/dist`
- [ ] Reload Caddy
- [ ] Verify accessible at `https://kei.binktogether.com`
- [ ] Commit: `feat: production build + caddy config`

---

## Part D: Tributary Integration

### Task D1: Pipe Snapshots to Kei API

**Files:**
- Modify: `~/Projects/tributary/scripts/anastasia-snapshot.js` — after writing JSON file, also POST to Kei API

Steps:
- [ ] Add fetch call to POST snapshot to `http://localhost:8081/api/snapshots` after file write
- [ ] Test by running snapshot script manually
- [ ] Verify new snapshot appears in Kei API
- [ ] Commit: `feat: pipe tributary snapshots to kei-api`

---

## Execution Order

A1 → A2 → A3 → A4 (API ready) → B1 → B2 → B3 → B4 → B5 → B6 → B7 (frontend done) → C1 (deployed) → D1 (live pipeline)

## Design Notes

- **Dark theme** — dark gray/slate base, accent colors per scope
- **Scope colors:** Home=#3B82F6 (blue), Salon=#EC4899 (pink), Woodwards=#F59E0B (amber), Synthhub=#8B5CF6 (purple)
- **Responsive** — works on tablet/desktop, mobile is nice-to-have
- **No SSR** — pure SPA, static files served by Caddy
- **PIN is UI-level only** — the real security boundary is Kei API's bearer token, which never leaves the server/env
