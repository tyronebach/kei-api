# Kei API Hardening — Implementation Plan

Based on Codex review analysis. Covers the "DO" items only — no over-engineering.

**Current state:** ~2,000 lines, 16 files, 0 tests, single bearer token, no migrations.
**Target state:** Multi-agent ready, validated, tested, auditable.

---

## Phase 0: Foundation (do first, everything else depends on it)

### 0A. Alembic Baseline
**Why first:** We're about to change the schema (soft delete columns, auth columns, FK constraints). Need migrations before touching models.

- `pip install alembic`, add to `requirements.txt`
- `alembic init alembic/`
- Configure `alembic/env.py` to import `db.models.Base` and read `DATABASE_URL` from config
- Generate baseline migration from current schema: `alembic revision --autogenerate -m "baseline"`
- Stamp existing DB as current: `alembic stamp head`
- Replace `Base.metadata.create_all()` in `main.py` lifespan with a no-op startup (no schema creation in app code)
- Run migrations in exactly one place: container entrypoint/start script before uvicorn (`alembic upgrade head`)
- Do not run Alembic from inside request lifecycle or FastAPI lifespan

**Files touched:** `requirements.txt`, `main.py`, new `alembic/` directory, `Dockerfile`
**Risk:** Low — baseline migration matches existing schema exactly

### 0B. Test Infrastructure
**Why first:** Can't safely refactor without tests. Write tests for current behavior, then each subsequent phase adds tests for its changes.

- Create `tests/` directory with `conftest.py`
- Test fixtures: temporary file-based SQLite DB (not in-memory), test client, auth header helper
- Run Alembic migrations in test setup so tests exercise real schema state
- **conftest.py** pattern:
  ```python
  import pytest
  from sqlalchemy import create_engine
  from sqlalchemy.orm import sessionmaker
  from tempfile import NamedTemporaryFile
  from fastapi.testclient import TestClient

  @pytest.fixture
  def db_engine():
      tmp = NamedTemporaryFile(suffix=".db")
      engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
      Base.metadata.create_all(engine)
      yield engine
      engine.dispose()
      tmp.close()

  @pytest.fixture
  def client(db_engine):
      TestingSessionLocal = sessionmaker(bind=db_engine)
      def _get_db():
          db = TestingSessionLocal()
          try:
              yield db
          finally:
              db.close()
      app.dependency_overrides[get_db] = _get_db
      app.dependency_overrides[verify_token] = lambda: "test-token"
      with TestClient(app) as c:
          yield c
      app.dependency_overrides.clear()
  ```
- **Initial test files** (cover current behavior as baseline):
  - `tests/test_entities.py` — CRUD, search, insights, activity, delete
  - `tests/test_transactions.py` — CRUD, filters, date range queries
  - `tests/test_items.py` — CRUD, search, adjust (in/out/adjustment), low-stock, movements
  - `tests/test_lists.py` — CRUD, position auto-assign, clear, checked filtering
  - `tests/test_services.py` — CRUD, listing filters
  - `tests/test_summary.py` — period resolution, trends, by-day, edge cases (empty DB, zero transactions)
  - `tests/test_auth.py` — valid token, invalid token, missing token
- Add `pytest`, `httpx` to `requirements.txt` (dev deps)
- Target: **~60-80 tests** covering happy paths + key edge cases for existing behavior

**Files touched:** `requirements.txt`, new `tests/` directory (8 files)
**Risk:** None — read-only verification of existing behavior

---

## Phase 1: Data Integrity (fix bugs and validation gaps)

### 1A. Input Validation Hardening — `schemas.py`
Tighten Pydantic models to reject garbage at the door.

**Changes:**
| Field | Current | Fix |
|-------|---------|-----|
| `TransactionCreate.amount` | `float` | `float` with `gt=0` (direction comes from `type`; amount is always magnitude) |
| `TransactionCreate.date` | `str` | Custom validator: parse with `date.fromisoformat()`, reject invalid, store as `YYYY-MM-DD` string |
| `EntityCreate.name` | `str` | `str` with `min_length=1` + strip whitespace validator |
| `ListItemCreate.content` | `str` | `str` with `min_length=1` + strip whitespace |
| `ServiceCreate.name` | `str` | `str` with `min_length=1` |
| `ServiceCreate.price` | `float` | `float` with `gt=0` (services must have positive price) |
| `ItemCreate.quantity` | `float = 0` | `float = 0` with `ge=0` (no negative starting stock) |
| `ItemAdjust.quantity` | `float` | Conditional validator: `in/out` require `gt=0`, `adjustment` allows `ge=0` |
| All `tags` fields | `list[str] \| None` | Add validator: strip whitespace, reject empty strings, deduplicate |
| All date query params | Raw strings passed to `datetime.strptime()` | Wrap in try/except → raise `HTTPException(422)` with message |

**Refund rule:** represent refunds as positive-magnitude records (`type="expense"` with optional `meta.refund_of`/`tags=["refund"]`), not negative amounts.

**Whitespace stripping pattern** (add to `StrictInput`):
```python
from pydantic import field_validator

class StrictInput(BaseModel):
    model_config = {"extra": "forbid"}

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v
```

**Date validation helper** (new in `schemas.py` or a `validators.py`):
```python
from datetime import date as date_type

def validate_date_str(v: str) -> str:
    try:
        date_type.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Invalid date format: '{v}'. Expected YYYY-MM-DD.")
    return v
```

**Tests to add:** `tests/test_validation.py` — invalid dates, empty names, zero amounts, negative stock, whitespace-only strings, empty tags

**Files touched:** `schemas.py`, date-parsing blocks in `routers/entities.py` and `routers/summary.py`

### 1B. Stock Adjustment Atomicity — `routers/items.py`
Fix the read-modify-write race condition in `adjust_item()`.

**Current flow (broken):**
```python
item = db.get(Item, item_id)        # READ
item.quantity += body.quantity       # MODIFY in Python
db.add(movement)                     # separate INSERT
db.commit()                          # WRITE
```

**Fixed flow:**
```python
from sqlalchemy import update

@router.post("/{item_id}/adjust")
def adjust_item(item_id: str, body: ItemAdjust, db: Session = Depends(get_db)):
    if body.type == "in":
        stmt = (
            update(Item)
            .where(Item.id == item_id)
            .values(quantity=Item.quantity + body.quantity)
        )
    elif body.type == "out":
        stmt = (
            update(Item)
            .where(Item.id == item_id, Item.quantity >= body.quantity)
            .values(quantity=Item.quantity - body.quantity)
        )
    elif body.type == "adjustment":
        stmt = (
            update(Item)
            .where(Item.id == item_id)
            .values(quantity=body.quantity)
        )

    result = db.execute(stmt)
    if result.rowcount == 0:
        # Either item doesn't exist or insufficient stock
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient stock: {item.quantity} {item.unit} available, requested {body.quantity}"
        )

    # Movement record in same transaction
    movement = ItemMovement(
        item_id=item_id,
        type=body.type,
        quantity=body.quantity,
        reason=body.reason,
        transaction_id=body.transaction_id,
    )
    db.add(movement)
    db.commit()

    item = db.get(Item, item_id)
    return {
        "data": ItemOut.model_validate(item),
        "meta": {"movement_id": movement.id},
    }
```

**Key change:** Single SQL UPDATE with WHERE guard. No Python-side arithmetic. Movement insert + quantity update in same commit = atomic.

**Tests to add:** `tests/test_item_adjust.py` — normal in/out/adjustment, insufficient stock (409), concurrent adjustment simulation

**Files touched:** `routers/items.py`

### 1C. Soft Delete + Foreign Keys — `db/models.py`, all routers
Replace hard deletes with soft deletes for auditable records. Add FK constraints.

**Migration preflight (required before adding FK constraints):**
1. Audit existing orphan references (`transactions.entity_id`, `item_movements.item_id`, `item_movements.transaction_id`)
2. Backfill/cleanup invalid refs before constraint migration (set nullable refs to `NULL`, remove or repair invalid non-null refs)
3. Record cleanup counts in migration output for traceability

**Schema changes (new migration):**
```python
# Add to Entity, Transaction, Item, Service, ListItem:
deleted_at: Mapped[int | None] = mapped_column(Integer, default=None, index=True)

# Add FK constraints:
class Transaction:
    entity_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entities.id", ondelete="SET NULL")
    )

class ItemMovement:
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("transactions.id", ondelete="SET NULL")
    )
```

**SQLite note:** FK changes often require table rebuild in SQLite. Use explicit Alembic `batch_alter_table` / create-copy-drop patterns, not naive autogen-only migration scripts.

**Router changes (all delete endpoints):**
```python
# Before:
db.delete(entity)

# After:
entity.deleted_at = int(time.time())

# All list/get/aggregate queries add:
q = q.filter(Entity.deleted_at.is_(None))
```

Apply non-deleted filtering to aggregate paths too (`summary`, `trends`, `by-day`, entity `activity`/`insights`) so deleted records never influence financial output.

**Helper** (to avoid repeating the filter everywhere — `db/helpers.py`):
```python
def active_query(db: Session, model):
    """Query only non-deleted records."""
    return db.query(model).filter(model.deleted_at.is_(None))
```

**Tests to add:** Soft delete behavior — deleted records excluded from listings and aggregate endpoints, GET by ID returns 404 after delete, FK cascade/set-null behavior

**Files touched:** `db/models.py`, all 6 router files, new `db/helpers.py`, new Alembic migration

### 1D. SQLite Busy Timeout — `db/connection.py`
One-line fix. Prevents "database is locked" under concurrent agent writes.

```python
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")  # wait up to 5s for locks
    cursor.close()
```

**Files touched:** `db/connection.py` (1 line)

### 1E. Date Parsing Safety — `routers/entities.py`, `routers/summary.py`
Wrap all `datetime.strptime()` / `date.fromisoformat()` calls in try/except → 422.

**Utility** (in a new `utils.py` or in `schemas.py`):
```python
from fastapi import HTTPException

def parse_date(value: str, param_name: str) -> str:
    """Validate and return YYYY-MM-DD string, or raise 422."""
    try:
        date.fromisoformat(value)
        return value
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date for '{param_name}': '{value}'. Expected YYYY-MM-DD."
        )
```

Apply to: `entities.py` insights endpoint (created_after/created_before), `summary.py` period resolution (custom from/to), trends endpoint.

**Files touched:** `routers/entities.py`, `routers/summary.py`, new `utils.py`

---

## Phase 2: Multi-Agent Auth & Scope Enforcement

This is the biggest change. New DB table, new auth flow, every endpoint gets scope checking.

### 2A. Agent Token Model — `db/models.py`, `config.py`
Replace single shared token with per-agent token table.

**New model:**
```python
class AgentToken(Base):
    __tablename__ = "agent_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_id)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # "rem", "minerva", "anastasia"
    token_hash: Mapped[str] = mapped_column(String, nullable=False)  # SHA-256 of bearer token
    allowed_scopes: Mapped[list] = mapped_column(JSON, nullable=False)  # ["salon"] or ["*"]
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=["read", "write"])  # ["read"] for read-only
    created_at: Mapped[int] = mapped_column(Integer, default=_now)
```

**Config change:**
```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/kei.db"
    api_token: str = "changeme"           # keep as fallback/admin token
    valid_scopes: list[str] = ["salon"]   # allowlist, validated on write
```

**Scope validation helper:**
```python
VALID_SCOPES = settings.valid_scopes  # or load from DB

def validate_scope(scope: str):
    if scope not in VALID_SCOPES:
        raise HTTPException(422, detail=f"Unknown scope: '{scope}'. Valid: {VALID_SCOPES}")
```

**Token management:** CLI script or admin endpoint to create/rotate tokens. Not a priority for now — seed them in a migration or startup script.

### 2B. Auth Rewrite — `dependencies.py`
Return a principal object instead of just validating the token.

```python
from dataclasses import dataclass

@dataclass
class AgentPrincipal:
    agent_id: str
    allowed_scopes: list[str]  # ["salon"] or ["*"]
    permissions: list[str]     # ["read", "write"]

    def can_access_scope(self, scope: str) -> bool:
        return "*" in self.allowed_scopes or scope in self.allowed_scopes

    def can_write(self) -> bool:
        return "write" in self.permissions

def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> AgentPrincipal:
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    agent_token = db.query(AgentToken).filter(AgentToken.token_hash == token_hash).first()

    if not agent_token:
        # Fallback: check legacy admin token
        if credentials.credentials == settings.api_token:
            return AgentPrincipal(agent_id="admin", allowed_scopes=["*"], permissions=["read", "write"])
        raise HTTPException(status_code=401, detail="Invalid token")

    return AgentPrincipal(
        agent_id=agent_token.agent_id,
        allowed_scopes=agent_token.allowed_scopes,
        permissions=agent_token.permissions,
    )
```

### 2C. Scope Enforcement — All Routers
Every endpoint that touches scoped data must check the principal.

**Pattern for list endpoints** (scope is optional query param):
```python
@router.get("")
def list_entities(
    scope: str | None = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = active_query(db, Entity)

    if scope:
        if not agent.can_access_scope(scope):
            raise HTTPException(403, detail=f"No access to scope '{scope}'")
        q = q.filter(Entity.scope == scope)
    elif "*" not in agent.allowed_scopes:
        # Non-wildcard agents only see their own scopes
        q = q.filter(Entity.scope.in_(agent.allowed_scopes))
    # else: wildcard agent sees everything (Anastasia)
    ...
```

**Pattern for by-ID endpoints** (must verify scope of fetched record):
```python
@router.get("/{entity_id}")
def get_entity(
    entity_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    entity = db.get(Entity, entity_id)
    if not entity or entity.deleted_at:
        raise HTTPException(404, detail="Entity not found")
    if not agent.can_access_scope(entity.scope):
        raise HTTPException(403, detail="No access to this record's scope")
    return {"data": EntityOut.model_validate(entity)}
```

**Pattern for write endpoints** (check scope + write permission):
```python
@router.post("")
def create_entity(
    body: EntityCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(403, detail="Read-only token")
    if not agent.can_access_scope(body.scope):
        raise HTTPException(403, detail=f"No write access to scope '{body.scope}'")
    validate_scope(body.scope)
    ...
```

**Shared helper** to reduce repetition (`db/helpers.py`):
```python
def get_scoped_or_404(db, model, record_id, agent):
    """Fetch by ID, verify not deleted, verify scope access."""
    record = db.get(model, record_id)
    if not record or record.deleted_at:
        raise HTTPException(404, detail=f"{model.__tablename__[:-1].title()} not found")
    if not agent.can_access_scope(record.scope):
        raise HTTPException(403, detail="No access to this record's scope")
    return record
```

### 2D. Actor Attribution — `db/models.py`, all create/update endpoints
Add `created_by` and `updated_by` to all scoped models.

```python
# Add to Entity, Transaction, Item, Service, ListItem:
created_by: Mapped[str | None] = mapped_column(String, default=None)
updated_by: Mapped[str | None] = mapped_column(String, default=None)
```

**Set on create:**
```python
entity = Entity(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
```

**Set on update:**
```python
entity.updated_by = agent.agent_id
```

These columns are informational — no logic depends on them. Just audit trail.

**Files touched:** `db/models.py`, `dependencies.py`, all 6 router files, `db/helpers.py`, new Alembic migration, schemas (add to Out models)
**Tests to add:** `tests/test_auth.py` expanded — per-agent tokens, scope isolation (Rem can't read Minerva's data), wildcard access, read-only tokens, 403 on cross-scope access

---

## Phase 3: Polish (small wins, low risk)

### 3A. Health Endpoint DB Check — `main.py`
```python
@app.get("/health")
def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
```

### 3B. Unused Tag Parameter — `routers/services.py`
The `tag` query param exists but does nothing. Add the same JSON tag filter used in entities:
```python
if tag:
    q = q.filter(
        text("EXISTS (SELECT 1 FROM json_each(services.tags) WHERE json_each.value = :tag)")
        .bindparams(tag=tag)
    )
```

### 3C. Structured Error Responses — `main.py`
Add a global exception handler for consistency:
```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status": exc.status_code,
            "message": exc.detail,
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "status": 422,
            "message": "Validation error",
            "details": exc.errors(),
        },
    )
```

### 3D. Summary Cross-Scope Breakdown
Add a `/api/summary/by-scope` endpoint for Anastasia:
```python
@router.get("/by-scope")
def get_summary_by_scope(
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)
    # Group by scope + type
    rows = db.query(
        Transaction.scope,
        Transaction.type,
        func.sum(Transaction.amount).label("total"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start, Transaction.date <= end
    ).group_by(Transaction.scope, Transaction.type).all()
    # ... format into per-scope breakdown
```

---

## Execution Order & Estimates

| Phase | What | Est. Time | Dependencies |
|-------|------|-----------|--------------|
| **0A** | Alembic baseline | 1-2 hrs | None |
| **0B** | Test infrastructure + baseline tests | 3-4 hrs | None (parallel with 0A) |
| **1A** | Validation hardening | 1-2 hrs | 0B (need tests) |
| **1B** | Stock adjustment atomicity | 1 hr | 0B |
| **1C** | Soft delete + FK constraints + orphan cleanup | 3-4 hrs | 0A (need migrations) |
| **1D** | SQLite busy_timeout | 5 min | None |
| **1E** | Date parsing safety | 30 min | None |
| **2A** | Agent token model | 1-2 hrs | 0A, 1C |
| **2B** | Auth rewrite | 1-2 hrs | 2A |
| **2C** | Scope enforcement (all routers) | 2-3 hrs | 2B |
| **2D** | Actor attribution columns | 1 hr | 2A |
| **3A-D** | Polish items | 1-2 hrs | 2C |
| | **Total** | **~16-22 hrs** | |

---

## What We're NOT Doing (and why)

| Codex Suggestion | Why Skip |
|------------------|----------|
| Category taxonomy (parent/child model) | Strings are fine. GROUP BY works. Don't build a taxonomy engine. |
| Recurring transactions resource | Agents have cron. Let them schedule their own creates. |
| Batch endpoints | Agents can loop. Add if latency becomes a real problem. |
| `meta` schema versioning | Defeats the flexibility. Promote keys to columns when stable. |
| Non-root Docker user | Home server, behind firewall. Doesn't matter. |
| `migrate_sheets.py` cleanup | One-time script. Already ran. Dead code. |
| Request correlation IDs | Nice but not needed until debugging multi-agent is actually painful. |
| Cursor-based pagination | Offset/limit is fine at our scale. |

---

## Open Decisions (need your call)

1. **Scope names:** What should Minerva's scope be? `sidehustle`? `minerva`? Something domain-specific?
2. **Token provisioning:** Seed tokens via migration script, CLI command, or admin endpoint? (I'd say migration script for now — we know the agents upfront.)
3. **Anastasia permissions:** Read-only across all scopes, or read-write on a `tax` / `finance` scope for her own planning data?

---

## Implementation Checklist (Go/No-Go Gates)

Use this as the execution gate. Do not start the next phase until the current one is green.

### Phase 0A — Alembic Baseline
- [ ] `alembic/` initialized and committed
- [ ] Baseline revision generated and reviewed (no unintended DDL)
- [ ] Existing DB stamped to `head` successfully
- [ ] `main.py` no longer calls `Base.metadata.create_all()`
- [ ] Startup path runs `alembic upgrade head` exactly once (entrypoint/prestart only)
- [ ] Fresh boot + restart succeed with no migration drift

### Phase 0B — Test Infrastructure
- [ ] `tests/` and `conftest.py` created
- [ ] Tests use file-based SQLite DB (not `:memory:`) with per-request sessions
- [ ] Dependency overrides cleaned up after each test
- [ ] Baseline CRUD/auth/summary tests exist and pass locally
- [ ] CI/local command (`pytest -q`) documented

### Phase 1A — Validation Hardening
- [ ] `amount > 0` enforced for transactions
- [ ] Date inputs validated to strict `YYYY-MM-DD`
- [ ] Empty/whitespace-only strings rejected for key name/content fields
- [ ] `ItemAdjust` validation is conditional by `type` (`adjustment` allows zero)
- [ ] Tags normalized (trimmed, non-empty, deduped)
- [ ] Validation tests added and passing

### Phase 1B — Stock Adjustment Atomicity
- [ ] `adjust_item()` uses guarded SQL `UPDATE` (no Python read-modify-write arithmetic)
- [ ] Insufficient stock returns deterministic error (`409` preferred)
- [ ] Quantity update + movement insert are in one transaction
- [ ] Concurrency test demonstrates no lost updates

### Phase 1C — Soft Delete + FK Constraints
- [ ] Preflight orphan audit script/query executed and results captured
- [ ] Orphan cleanup/backfill completed before FK migration
- [ ] Alembic migration uses SQLite-safe table rebuild/batch operations
- [ ] All delete endpoints switched to soft delete
- [ ] All reads, including aggregate endpoints, exclude soft-deleted rows
- [ ] FK behavior verified (`SET NULL` / `CASCADE`) with tests

### Phase 1D — SQLite Busy Timeout
- [ ] `PRAGMA busy_timeout` added on connection
- [ ] Concurrent write smoke test passes without flaky lock failures

### Phase 1E — Date Parsing Safety
- [ ] All date query params parsed via shared validator/helper
- [ ] Invalid dates return `422` (not `500`)
- [ ] Regression tests for bad date input added and passing

### Phase 2A — Agent Token Model
- [ ] `agent_tokens` model + migration added
- [ ] Token hashing implemented (no plaintext token storage)
- [ ] Scope allowlist validation strategy finalized
- [ ] Seed strategy for initial tokens implemented

### Phase 2B — Auth Rewrite
- [ ] Auth dependency returns principal (`agent_id`, scopes, permissions)
- [ ] Legacy admin token fallback behavior explicit and tested
- [ ] Invalid token path returns consistent `401`

### Phase 2C — Scope Enforcement
- [ ] All list endpoints enforce allowed scope filtering
- [ ] All by-ID endpoints verify record scope before returning/updating/deleting
- [ ] All write endpoints check write permission + scope access
- [ ] Cross-scope access tests pass (`403` where expected)

### Phase 2D — Actor Attribution
- [ ] `created_by` / `updated_by` columns added and migrated
- [ ] Create/update handlers populate attribution fields
- [ ] Out schemas include attribution fields where needed
- [ ] Audit trail tests pass

### Phase 3A-D — Polish
- [ ] `/health` checks DB connectivity and returns `503` on failure
- [ ] `services` `tag` filter implemented or removed (no dead param)
- [ ] Error response shape standardized and documented
- [ ] `/api/summary/by-scope` implemented with scope-aware auth checks

### Final Go/No-Go
- [ ] Full test suite green
- [ ] Manual smoke test of all resources complete
- [ ] Migration rollback/restore path validated on a backup copy
- [ ] Deployment playbook updated (migrate, start, verify, rollback)
