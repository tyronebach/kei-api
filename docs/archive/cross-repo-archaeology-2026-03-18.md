# Cross-Repo Archaeology: Kei-API + Tributary — 2026-03-18

## Coupling Map

```
┌─────────────────────────────────────────────┐
│                 TRIBUTARY                     │
│                                              │
│  Plaid API ──→ sync ──→ reconcile ──→ rules │
│  CSV files ──→ import ─┘                     │
│                                              │
│  export/kei-export.ts ────HTTP POST──────────┼──→ Kei /api/transactions
│  export/kei-export.ts ────HTTP GET───────────┼──→ Kei /api/transactions
│  export/kei-export.ts ────HTTP PATCH─────────┼──→ Kei /api/transactions/:id
│  export/kei-import.ts ────HTTP GET───────────┼──→ Kei /api/transactions
│  audit.ts ────docker exec python3────────────┼──→ Kei SQLite directly
│                                              │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│                   KEI-API                     │
│                                              │
│  routers/transactions.py                      │
│    ├── Accepts external_source="tributary"    │
│    ├── external_id for idempotency            │
│    ├── Fuzzy reconcile (claim Rem rows)       │
│    └── PATCH for Tributary to claim rows      │
│                                              │
│  schemas.py                                   │
│    ├── TransactionCreate.external_source      │
│    └── TransactionCreate.external_id          │
│                                              │
│  summary.py                                   │
│    └── source=bank maps to external_source    │
│                                              │
└──────────────────────────────────────────────┘
```

**Coupling level: Loose but real.** Kei works without Tributary. Tributary depends on Kei for transaction storage and the household-facing API. The `external_source/external_id` mechanism is generic (could serve other importers), but in practice only Tributary uses it.

## Integration Points (detailed)

### 1. HTTP API (healthy)

| Tributary calls | Kei endpoint | Purpose |
|----------------|--------------|---------|
| `createTransaction()` | `POST /api/transactions` | Push reconciled canonical rows |
| `findTransactionByExternalId()` | `GET /api/transactions?external_source=tributary&external_id=X` | Idempotency check |
| `fetchAllTransactions()` | `GET /api/transactions` | Pre-export fuzzy match against manual Rem entries |
| `patchTransaction()` | `PATCH /api/transactions/:id` | Update category/description after rule changes |

**Config:** `KEI_API_URL` + `KEI_API_TOKEN` in Tributary's `.env`.

### 2. Docker exec (problematic)

`audit.ts` runs:
```javascript
docker exec kei-api python3 -c "
  import sqlite3
  conn = sqlite3.connect('/app/data/kei.db')
  // queries soft-deletes, duplicates, active count
"
```

**Problems:**
- Bypasses Kei's API and auth layer entirely
- Assumes Docker container name, mount paths, Python availability
- Breaks if Kei moves off SQLite or changes schema
- No error contract — parses stdout JSON

### 3. Shared Concepts (implicit contract)

| Concept | Kei representation | Tributary representation |
|---------|-------------------|------------------------|
| Scope | `scope` field (home/salon/woodwards/synthhub) | `household_scope` via `keiScope()` mapping (currently 1:1) |
| Transaction identity | `(external_source, external_id)` unique | `canonical_transaction.id` as `external_id` |
| Amount | Integer cents internally, float dollars in API | Integer cents internally, float dollars in API |
| Categories | Free-text `category` field | `category_final` from rules engine |
| Fuzzy matching | Server-side in `_find_fuzzy_duplicate_tributary()` | Client-side pre-export in `kei-export.ts` |

**Note:** Both sides do fuzzy matching independently. Tributary pre-filters before sending; Kei re-checks on receive. This is documented as defense-in-depth.

### 4. Shared Type (no formal contract)

Tributary defines `KeiTransaction` interface in `kei-client.ts`:
```typescript
interface KeiTransaction {
  id: string;
  scope: string;
  type: string;
  amount: number;
  category: string;
  // ...
}
```

Kei defines `TransactionOut` in `schemas.py`:
```python
class TransactionOut(BaseModel):
    id: str
    scope: str
    type: str
    amount: float
    category: str
    # ...
```

**These are not linked.** A field rename in Kei silently breaks Tributary.

---

## What Should Merge, Split, or Change

### Cross-repo changes needed

| # | Change | Why | Effort |
|---|--------|-----|--------|
| 1 | **Add `/api/audit` endpoint to Kei** | Replace `docker exec` in Tributary's `audit.ts`. Kei should own its own integrity checks. Tributary calls the endpoint instead of reaching into the DB. | Medium |
| 2 | **Shared API contract validation** | Either: (a) Kei generates OpenAPI spec, Tributary validates against it in CI. Or (b) shared JSON schema file that both repos import. Prevents silent breakage. | Medium |
| 3 | **Move `fetchAllTransactions()` to server-side** | Tributary currently pulls ALL Kei transactions for fuzzy matching. As data grows, this becomes a bottleneck. Add a `/api/transactions/match` endpoint to Kei that accepts amount+date+scope and returns candidates. | Medium |

### Things that should NOT merge

- **The repos themselves.** Kei is a general-purpose small-business API. Tributary is a household finance pipeline. Different lifecycles, different deployment targets. Loose coupling is correct.
- **The CLIs.** `kei` CLI is for business operations (entity management, manual transactions). `tributary` CLI is for pipeline operations (sync, reconcile, export). Different audiences, different cadences.
- **The databases.** Kei's SQLite is the system of record for business data. Tributary's SQLite is the ingestion staging area. Separation of concerns is correct.

### Both CLIs — shared patterns worth noting

| Aspect | Kei CLI | Tributary CLI |
|--------|---------|---------------|
| Framework | Typer (Python) | Commander (TypeScript) |
| Config | YAML (`~/.config/kei/config.yaml`) | `.env` file |
| Auth | Bearer token via config | Bearer token via env |
| Scope | `--scope` flag / `KEI_SCOPE` env | Per-account via rules |
| Output | Rich tables | console.log/table |

No unification needed — different languages, different purposes.

---

## Combined Technical Debt Register (ranked)

Cross-repo items are marked with **(X)**.

| # | Item | Repo | Impact | Effort | Category |
|---|------|------|--------|--------|----------|
| 1 | **(X) Docker exec coupling in audit.ts** | Tributary→Kei | High | Medium | Architecture |
| 2 | **(X) No API contract tests** | Both | High | Medium | Reliability |
| 3 | **Test coverage gaps** | Tributary | High | High | Quality |
| 4 | **Extract CRUD boilerplate** (write-guard, scope-auth, soft-delete, update) | Kei | High | Low | DRY |
| 5 | **(X) `fetchAllTransactions()` full scan** | Tributary→Kei | Medium | Medium | Performance |
| 6 | **Split queries.ts monolith** | Tributary | Medium | Medium | Maintainability |
| 7 | **Split cli.ts monolith** | Tributary | Medium | Medium | Maintainability |
| 8 | **Stale backup files** | Tributary | Low | Low | Hygiene |
| 9 | **Dead `pdf_line` source type** | Tributary | Low | Low | Hygiene |
| 10 | **Inconsistent view usage** | Tributary | Low | Low | Consistency |
| 11 | **CLI naming drift** (`tx` vs `transaction`) | Kei | Low | Low | Cosmetic |

### Quick wins (do first)

1. **Kei: extract CRUD helpers** — purely mechanical, high repetition reduction, zero risk
2. **Tributary: delete `.bak` files** — 30 seconds
3. **Tributary: bundle pre-export precondition checks** — small refactor, cleaner code

### Strategic investments (plan for)

1. **Add `/api/audit` to Kei, remove Docker exec from Tributary** — eliminates the single most fragile coupling point
2. **API contract validation in CI** — prevents the silent-breakage failure mode
3. **Server-side match endpoint** — future-proofs export performance
