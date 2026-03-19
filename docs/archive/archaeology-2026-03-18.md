# Kei-API Repo Archaeology — 2026-03-18

## 1. Subsystem Map

```
kei-api/
├── main.py                    FastAPI app, CORS, exception handlers, startup checks
├── config.py                  Settings from env vars
├── dependencies.py            Bearer token auth, AgentPrincipal model (read/write, scopes)
├── schemas.py                 Pydantic input/output models (extra: "forbid")
├── search.py                  Fuzzy matching engine (rapidfuzz + Soundex)
├── utils.py                   Date parsing
├── db/
│   ├── connection.py          Engine, session factory, SQLite pragmas
│   ├── models.py              7 ORM tables: Entity, Transaction, Item, Service,
│   │                          ListItem, ItemMovement, AgentToken
│   └── helpers.py             active_query(), apply_scope_filter(), get_scoped_or_404()
├── routers/
│   ├── entities.py            CRUD + insights + activity aggregation + fuzzy search
│   ├── transactions.py        CRUD + fuzzy dedup + Tributary reconciliation (largest, 16.7 KB)
│   ├── items.py               CRUD + stock adjust + movement audit trail
│   ├── services.py            CRUD (simplest, 3.6 KB)
│   ├── lists.py               Named lists with position tracking + bulk clear
│   └── summary.py             Trends, by-scope, by-day, by-month analytics (17.2 KB)
├── cli/kei/                   Separate installable CLI package
│   └── kei/
│       ├── cli.py             Typer app, 6 subcommand groups
│       ├── client.py          HTTP wrapper with error handling + scope injection
│       ├── config.py          YAML config (~/.config/kei/config.yaml)
│       ├── entities.py        entity add/list/search/get/update/delete/activity/insights
│       ├── transactions.py    tx add/list/get/update/link/delete
│       ├── items.py           item add/list/search/get/adjust/movements/update/delete
│       ├── services.py        service add/list/get/update/delete
│       ├── lists.py           list names/show/add/check/uncheck/clear/delete
│       ├── summary.py         summary overview/trends/by-day/by-scope/by-month
│       └── utils.py           resolve_id() (short ID prefix lookup)
├── alembic/                   7 migrations (baseline → payment_method_constraint)
└── tests/                     17 test files including reconcile E2E scenarios
```

**Resource domains:** Entities, Transactions, Items, Services, Lists, Summary.
**API surface:** 50+ endpoints, all JSON with `{"data": ...}` envelope.
**Auth model:** Agent-principal with bearer tokens, per-scope read/write grants.
**CLI framework:** Typer (Python), mirrors API 1:1.

### Dependency Flow

```
main.py → routers/* → db/{models,helpers,connection} + schemas + search + dependencies
                                                         ↓
                                                    config.py
```

No circular dependencies. Clean linear layering.

---

## 2. Dead Files, Duplicates, Stale Patterns

### Dead / Removed (clean)

| What | When | Notes |
|------|------|-------|
| `routers/recurring.py` | Mar 11 | Feature removed, router + CLI + tests all deleted together |
| `cli/kei/kei/recurring.py` | Mar 11 | Same cleanup |
| `tests/test_recurring.py` | Mar 11 | Same cleanup |
| `migrate_sheets.py` | Feb 18 | One-time migration script, deleted |

No orphan files remain. No commented-out code blocks. All test files have corresponding source.

### Duplicate Logic

**High-impact repeats (5+ occurrences):**

1. **Write-permission guard** — identical in every mutable endpoint:
   ```python
   if not agent.can_write(): raise HTTPException(403, "Read-only token")
   ```
   Appears in: entities, transactions, items, services, lists.

2. **Scope validate + authorize** — ~50 occurrences:
   ```python
   validate_scope(body.scope)
   if not agent.can_access_scope(body.scope):
       raise HTTPException(403, f"No write access to scope '{body.scope}'")
   ```

3. **Soft-delete boilerplate** — 5 routers, identical pattern:
   ```python
   entity.deleted_at = int(time.time())
   entity.updated_by = agent.agent_id
   db.commit()
   return {"data": {"id": entity_id, "deleted": True}}
   ```

4. **Update boilerplate** — 3+ routers:
   ```python
   for key, value in body.model_dump(exclude_unset=True).items():
       setattr(item, key, value)
   item.updated_by = agent.agent_id
   db.commit()
   ```

5. **Pagination envelope** — every list endpoint:
   ```python
   total = q.count()
   items = q.order_by(...).offset(offset).limit(limit).all()
   return {"data": [...], "meta": {"count": len(items), "total": total}}
   ```

**Intentionally different (not duplicates):**
- `_fuzzy_score()` vs `_fuzzy_score_amount_date_only()` — defense-in-depth design, documented in README.

### Naming Drift (minor)

| Where | Issue |
|-------|-------|
| CLI subcommands | `entity` (singular) vs `items` endpoint (plural) — minor, CLI convention is singular |
| CLI function names | `tx_create()` mixes abbreviation (`tx`) with spelled-out elsewhere |
| Summary filter | `source=bank` maps to `external_source=="tributary"` — intentional abstraction, not drift |

No camelCase/snake_case inconsistencies. DB columns, JSON keys, and Python code are all consistently snake_case.

---

## 3. Merge / Split / Rename Recommendations

### Extract (from existing modules)

| What | From | Why |
|------|------|-----|
| `require_write_access()` dependency | Each router | Eliminates 5 identical permission guards |
| `validate_and_authorize_scope()` | Each router | Combines two-step scope check into one call |
| `perform_soft_delete(db, obj, agent)` | Each router | Standardizes soft-delete pattern |
| `perform_update(db, obj, body, agent)` | Each router | Standardizes update-from-body pattern |

All four would live in `dependencies.py` or `db/helpers.py`. No new files needed.

### Split consideration

| Module | Size | Recommendation |
|--------|------|----------------|
| `transactions.py` (router) | 16.7 KB | Could split reconciliation logic into `reconcile.py`, but current size is manageable |
| `summary.py` (router) | 17.2 KB | Analytics-heavy but cohesive; leave as-is |
| `schemas.py` | Single file | Could split per-resource, but single file aids discoverability; leave as-is |

### No merges needed

All modules have distinct responsibilities. Nothing overlaps enough to justify merging.

---

## 4. Technical Debt Register

Ranked by **impact** (how much it hurts) vs **effort** (how hard to fix).

| # | Item | Impact | Effort | Notes |
|---|------|--------|--------|-------|
| 1 | **Extract write-permission + scope-auth dependencies** | High | Low | Eliminates ~50 repeated blocks. Pure mechanical refactor. FastAPI `Depends()` makes this clean. |
| 2 | **Extract soft-delete + update helpers** | Medium | Low | 5 identical soft-delete blocks, 3+ update blocks. Move to `db/helpers.py`. |
| 3 | **Audit.ts Docker exec coupling** (cross-repo) | High | Medium | Tributary queries Kei's SQLite directly via `docker exec`. Add a `/api/audit` endpoint to Kei instead. |
| 4 | **No API versioning or contract tests** | Medium | Medium | Tributary depends on Kei's response shape. A breaking change in schemas.py silently breaks exports. Add contract tests or OpenAPI spec validation. |
| 5 | **Pagination helper** | Low | Low | Every list endpoint rebuilds the same offset/limit/count/envelope. Could be a generic function, but explicit code is also fine. |
| 6 | **transactions.py size** | Low | Medium | At 16.7 KB it's the largest router. Reconciliation logic could move to a separate module, but it's cohesive enough as-is. |
| 7 | **CLI abbreviation inconsistency** | Low | Low | `tx` vs `transaction` in function names. Cosmetic. |

### Not debt (intentional design)

- Dual fuzzy-scoring functions (defense-in-depth)
- Cents storage with dollar API (documented conversion)
- Dual Rem/Tributary write paths (multi-agent support)
