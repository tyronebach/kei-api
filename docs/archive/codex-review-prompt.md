# Kei API — Code Review Prompt

## Context

You are reviewing **Kei API** (`/home/tbach/Projects/kei-api/`), a FastAPI + SQLite REST API designed to be consumed exclusively by LLM agents (not humans). It currently manages a household hair salon and personal finances, and is expanding to serve additional agent consumers for financial planning and personal assistant tasks.

### Current Consumers
- **Rem** — household/salon management agent (entities, transactions, inventory, lists, services, summaries)

### Planned Consumers (expanding to)
- **Minerva** — personal assistant agent managing a side hustle (will need its own scopes, transaction categories, possibly recurring transactions and invoicing)
- **Anastasia** — tax accountant agent doing financial planning, cross-scope reporting, and overall fiscal picture (needs reliable aggregation, date range queries, category taxonomies, audit trails)

### What This API Is NOT
- Not human-facing (no UI, no browser clients)
- Not public internet-facing (runs on a home server behind a firewall, accessed only by trusted agents on the same network)
- Not high-traffic (low volume, handful of agent callers)

### Codebase Size
~2,000 lines of Python across 16 files. Small, focused, deliberately minimal.

### Stack
| Layer | Tech |
|-------|------|
| Framework | FastAPI (sync endpoints) |
| Database | SQLite (WAL mode, single file) |
| ORM | SQLAlchemy 2.x (mapped_column style) |
| Validation | Pydantic 2.x (strict input with `extra="forbid"`) |
| Search | rapidfuzz + custom Soundex |
| Auth | Single bearer token |
| IDs | UUID hex (uuid4) |
| Timestamps | Unix epoch integers |
| Deployment | Docker (python:3.12-slim) |

---

## Review Scope

Review the entire codebase with these priorities. The API is growing from 1 agent consumer to 3, with different needs (salon ops, side hustle management, tax/financial planning). Focus on what needs to harden for that expansion.

### 1. Data Integrity & Safety (HIGH PRIORITY)
- **Transaction safety:** Are writes atomic? Can concurrent agent requests corrupt data? SQLite WAL + single-writer is fine for our scale, but are there race conditions in the Python layer (e.g., read-then-write patterns in stock adjustments, summary calculations)?
- **Cascade / orphan risks:** Entities can be deleted while transactions reference their `entity_id`. Is this a problem? Should we add foreign keys or soft deletes?
- **Data validation:** Are there edge cases where bad data slips through? (e.g., negative amounts, future dates, empty strings for required fields, duplicate entity names)
- **Backup/recovery:** Any suggestions for SQLite backup strategy that works well with WAL mode?

### 2. Multi-Agent Readiness (HIGH PRIORITY)
- **Scope isolation:** Currently `scope` is a free-form string. Is this sufficient, or should scopes be a first-class table? Could one agent accidentally read/write another agent's scope?
- **Agent attribution:** There's no tracking of *which agent* created/modified a record. Should we add a `created_by` / `updated_by` field for audit trail?
- **Permission model:** Currently single shared token. As we add Minerva and Anastasia, should each agent have its own token with scope restrictions? What's the minimal change to support this?
- **Concurrent access:** Multiple agents hitting the API simultaneously — any SQLite locking concerns at our scale?

### 3. Schema & API Design (MEDIUM PRIORITY)
- **Missing features for financial planning:** Anastasia needs cross-scope aggregation, date-range breakdowns, category hierarchies, maybe budget tracking. What's missing from the current summary endpoints?
- **Recurring transactions:** Side hustle likely has recurring income/expenses. Should this be a new resource or a flag on transactions?
- **Bulk operations:** Agents sometimes need to create multiple records in one call (e.g., "log 5 transactions from today"). Worth adding batch endpoints?
- **Pagination consistency:** Is the offset/limit pattern sufficient, or should we add cursor-based pagination for large datasets?
- **Date handling:** Dates are stored as strings (`YYYY-MM-DD`). Is this fine for SQLite date functions, or should we normalize?
- **The `meta` JSON field:** Great for flexibility, but could become a dumping ground. Any suggestions for keeping it useful without it becoming unqueryable chaos?

### 4. Error Handling & Robustness (MEDIUM PRIORITY)
- **Error responses:** Are errors consistent and agent-friendly? Do they give enough context for an LLM to self-correct?
- **Input sanitization:** Any injection risks via the `meta` JSON field, tag arrays, or the raw SQL `text()` calls (e.g., the JSON tag query in entities)?
- **Edge cases:** What happens with empty databases, zero transactions in a period, division by zero in averages/trends?
- **Idempotency:** Should creates be idempotent? (e.g., agent retries a failed request and accidentally creates a duplicate transaction)

### 5. Code Quality & Maintainability (MEDIUM PRIORITY)
- **Router size:** `entities.py` (293 lines) and `summary.py` (285 lines) are the largest. Should any logic be extracted to service layers?
- **Test coverage:** There are no tests in the repo. What's the minimal test strategy for an API like this? What should be tested first?
- **Type safety:** Are there any type annotation gaps or Pydantic model inconsistencies?
- **DRY violations:** Any repeated patterns that should be abstracted?

### 6. Deployment & Operations (LOW PRIORITY)
- **Health endpoint:** Currently just returns `{"status": "ok"}`. Should it check DB connectivity?
- **Logging:** There's no structured logging. What's the minimal useful logging for debugging agent issues?
- **Database migrations:** Currently using `create_all()` on startup. Fine for now, but what's the path to handling schema changes without data loss?
- **Docker:** Any improvements to the Dockerfile or compose setup? (We just fixed a healthcheck issue — `curl` wasn't installed in slim image.)

---

## What NOT to Review
- Don't suggest switching from SQLite (it's the right choice for our scale)
- Don't suggest async endpoints (sync is fine for our load)
- Don't suggest adding a frontend or OpenAPI UI customizations
- Don't suggest microservices architecture
- Don't suggest adding rate limiting (trusted agents only)
- Don't worry about horizontal scaling

## Output Format

For each finding:
1. **What:** The specific issue or improvement
2. **Why it matters:** Concrete risk or benefit, especially in the context of expanding to 3 agent consumers
3. **Suggested fix:** Code-level recommendation (pseudocode or actual patches welcome)
4. **Priority:** Critical / High / Medium / Low

Group findings by the review categories above. Be specific — reference actual file names, line numbers, and function names. Don't pad with generic best practices; focus on what's actually relevant to this codebase and its expansion trajectory.
