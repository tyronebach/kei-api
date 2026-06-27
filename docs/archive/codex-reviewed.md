 Reviewed CODEX_REVIEW_PROMPT.md and the full codebase (main.py, config.py, dependencies.py, db/*, routers/*, schemas.py, search.py, migrate_sheets.py, Docker files). Static review only.

  1. Data Integrity & Safety

  1. What: Stock adjustment is a non-atomic read/modify/write flow in routers/items.py:141, routers/items.py:146, routers/items.py:165, and adjustment quantity is unconstrained in schemas.py:187.
     Why it matters: Concurrent agent requests can lose updates or oversell inventory; negative quantities can invert operations.
     Suggested fix: Use a single conditional SQL update (UPDATE ... WHERE quantity >= :q) and check rowcount; insert ItemMovement in the same transaction; enforce quantity > 0.
     Priority: Critical
  2. What: Referential integrity is not enforced (Transaction.entity_id in db/models.py:52, ItemMovement.item_id in db/models.py:100, ItemMovement.transaction_id in db/models.py:104), while hard deletes occur in routers/entities.py:291 and routers/items.py:191.
     Why it matters: Orphans break auditability and produce misleading summary/activity outputs as data volume grows.
     Suggested fix: Add foreign keys with explicit ondelete behavior (SET NULL or CASCADE) or move to soft-delete for auditable records.
     Priority: High
  3. What: Core value/date fields are weakly validated: schemas.py:65, schemas.py:68, schemas.py:187, schemas.py:211, plus required strings can be empty (schemas.py:18, schemas.py:161).
     Why it matters: Invalid financial records (negative amounts, malformed dates, blank names/content) leak into DB and later cause runtime failures.
     Suggested fix: Pydantic constraints (gt=0, min_length=1, date type or strict ISO validator) and whitespace normalization.
     Priority: High
  4. What: No backup/recovery workflow is implemented (only WAL/pragma setup in db/connection.py:19).
     Why it matters: SQLite is reliable here, but without scheduled backups/restores, recovery risk is high.
     Suggested fix: Add scheduled .backup snapshots, off-host retention, and restore drills; document WAL-safe procedure.
     Priority: Medium

  2. Multi-Agent Readiness

  1. What: Object-by-id endpoints do not enforce scope isolation (routers/transactions.py:72, routers/entities.py:181, routers/items.py:108, routers/services.py:52, routers/lists.py:105).
     Why it matters: With multiple agents/tokens, any agent with an ID can read/modify another scope’s records.
     Suggested fix: Return a principal from auth containing allowed scopes, and enforce scope in every query/update/delete.
     Priority: Critical
  2. What: Auth is a single shared token (config.py:6, dependencies.py:12), and models lack actor attribution fields.
     Why it matters: No per-agent permissions, no audit trail for who changed data.
     Suggested fix: Token table (hashed token, agent_id, allowed scopes/permissions) plus created_by/updated_by columns populated from auth context.
     Priority: High
  3. What: scope is free-form text across tables (db/models.py:24, db/models.py:46, db/models.py:65, db/models.py:87, db/models.py:113).
     Why it matters: Typos silently create new namespaces and fragment data across agents.
     Suggested fix: Introduce canonical scopes (table or strict allowlist) and validate on write.
     Priority: Medium

  3. Schema & API Design

  1. What: Summary APIs are mostly aggregate totals without scoped breakdown/taxonomy constructs (routers/summary.py:160).
     Why it matters: Anastasia’s planning use case needs by-scope/by-category/by-period drilldowns and consistent category structures.
     Suggested fix: Add endpoints for grouped breakdowns (scope/category/month), and a category taxonomy model (with optional parent/child).
     Priority: High
  2. What: No recurring transaction resource exists (only one-off transactions in db/models.py:36, single-create endpoint in routers/transactions.py:17).
     Why it matters: Minerva side-hustle workflows will generate repeat entries and retry patterns.
     Suggested fix: Add recurring_rules + materialized generated transactions (or preview + apply flow).
     Priority: Medium
  3. What: No batch create endpoints for high-frequency agent actions (routers/transactions.py:17, routers/lists.py:76, routers/items.py:24).
     Why it matters: Multiple single calls increase latency and partial failure surface.
     Suggested fix: Add bulk endpoints with transactional mode and per-row result map.
     Priority: Medium
  4. What: meta is fully unconstrained JSON in multiple models (db/models.py:31, db/models.py:55, db/models.py:73, db/models.py:120).
     Why it matters: Useful flexibility can degrade into unqueryable inconsistent blobs.
     Suggested fix: Add meta_schema_version, per-resource allowlisted keys, and promote high-value keys to typed columns when stabilized.
     Priority: Medium

  4. Error Handling & Robustness

  1. What: Invalid date input can raise 500s (e.g., routers/entities.py:128, routers/entities.py:157, routers/summary.py:40, routers/summary.py:134).
     Why it matters: Agents get server errors instead of actionable corrections.
     Suggested fix: Central date parsing/validation with 422 responses and machine-readable error codes.
     Priority: High
  2. What: SQLite contention handling is minimal (no busy_timeout or retry policy in db/connection.py:19).
     Why it matters: Multi-agent concurrent writes can produce intermittent database is locked.
     Suggested fix: Set PRAGMA busy_timeout, and add bounded retry for transient write conflicts.
     Priority: Medium
  3. What: Error payloads are inconsistent/simple strings (dependencies.py:15, multiple HTTPException sites in routers).
     Why it matters: LLM clients recover better from structured errors than free-form detail strings.
     Suggested fix: Global exception handlers returning {error, message, field, hint}.
     Priority: Medium
  4. What: tag query param exists but is unused in services listing (routers/services.py:29).
     Why it matters: Silent no-op query parameters confuse agent behavior.
     Suggested fix: Implement tag filtering or remove the parameter.
     Priority: Low

  5. Code Quality & Maintainability

  1. What: No automated tests are present (no tests/ in repository).
     Why it matters: High regression risk while introducing multi-agent auth/scope changes.
     Suggested fix: Start with integration tests for auth/scope isolation, stock adjustment concurrency, summary date validation, and delete/reference behavior.
     Priority: High
  2. What: Repeated CRUD/update patterns across routers (routers/entities.py:279, routers/items.py:179, routers/services.py:66, routers/transactions.py:86).
     Why it matters: Security/validation fixes must be replicated manually and are easy to miss.
     Suggested fix: Extract shared helpers/service layer (get_scoped_or_404, patch/update utilities, standardized error mapping).
     Priority: Medium
  3. What: Migration script has correctness/security issues: hardcoded token/account (migrate_sheets.py:10, migrate_sheets.py:31) and likely skips first data row (migrate_sheets.py:49, migrate_sheets.py:82).
     Why it matters: Risk of incomplete imports and credential leakage.
     Suggested fix: Move secrets to env vars; remove double header-skip logic.
     Priority: Low

  6. Deployment & Operations

  1. What: Health endpoint does not verify DB connectivity (main.py:25).
     Why it matters: Service can report healthy while DB is unavailable/locked.
     Suggested fix: Add lightweight DB check (SELECT 1) in /health.
     Priority: Medium
  2. What: Schema evolution relies on create_all() at startup (main.py:11).
     Why it matters: Future schema changes for multi-agent features risk destructive/manual migrations.
     Suggested fix: Introduce Alembic baseline now, before further model expansion.
     Priority: Medium
  3. What: No structured request logging/correlation IDs in API paths.
     Why it matters: Hard to debug agent misbehavior and cross-agent incidents.
     Suggested fix: Add middleware logging (request_id, agent_id, route, status, latency) and include agent context.
     Priority: Medium
  4. What: Container runs as root by default (Dockerfile:1).
     Why it matters: Unnecessary privilege for home-server deployment.
     Suggested fix: Add non-root user and run app under that user.
     Priority: Low

  Open questions/assumptions:

  1. Is cross-scope read intended for all agents, or only Anastasia? This determines whether “omit scope = all” remains default.
  2. Should refunds be represented as type=expense (current migration behavior) or signed income with explicit refund category?
  3. Are duplicate entity names acceptable within a scope, or should there be optional dedupe constraints?
