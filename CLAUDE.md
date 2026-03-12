# CLAUDE.md — Kei API + CLI

Agent-first data API for LLM assistants. Domain-agnostic — `scope` field namespaces everything. `meta` JSON handles domain-specific data without schema changes.

## Stack
- **API:** FastAPI + SQLAlchemy + Alembic + SQLite (`kei.db`)
- **CLI:** Python package at `cli/kei/` (installable via `pip install -e .`)
- **Auth:** Single bearer token (`KEI_API_TOKEN` env var)
- **Orchestration:** Docker (`docker-compose.yml`) or local venv

## Validation Hierarchy
1. Local venv (preferred): `cd /path && .venv/bin/python -m pytest tests/ -q`
2. Docker: `docker compose exec api python -m pytest tests/ -q`

Never use host-global `pytest` or `python`.

If venv missing:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Commands
```bash
# API — local dev
source .venv/bin/activate
alembic upgrade head
uvicorn main:app --port 8081 --reload

# API — Docker
docker compose up --build

# CLI — install
cd cli/kei && pip install -e .

# CLI — dev usage
export KEI_API_BASE=http://127.0.0.1:8081
export KEI_API_TOKEN=test-token
python -m kei.cli health
```

## Commit Convention
- Conventional commits to `main`: `feat:` `fix:` `refactor:` `docs:` `test:`
- No branches
- Schema changes must include an Alembic migration

## Implementation Rules
- **Alembic migrations for all schema changes.** Never use `Base.metadata.create_all()` to evolve schema in production — that's handled in the container entrypoint.
- **Don't break multi-agent.** The `scope` field namespaces data; never let one scope bleed into another.
- **`meta` JSON is the extension point.** Domain-specific fields go there, not new columns.
- Read `IMPLEMENTATION_PLAN.md` before starting any significant work — it documents phased hardening decisions.

## Hard-Cut Product Policy
- Optimize for one canonical current-state implementation.
- Do **not** preserve or add compatibility bridges, migration shims, silent fallbacks, compact adapters, or dual paths for historical local states unless explicitly requested.
- Prefer one canonical codepath, fail-fast diagnostics, and explicit recovery steps.
- If temporary transition code is unavoidable, document in the same diff: why it exists, why the canonical path is insufficient, exact deletion criteria, and the tracking ADR/task.
- Default stance: delete old-state compatibility code instead of carrying it forward.

## Resource Types
`entities`, `items`, `lists`, `transactions`, `services`, `recurring`, `summary`
All share: `id`, `scope`, `meta` (JSON), standard timestamps.

## High-Risk Areas
- Alembic migration chain — always run `alembic current` + `alembic heads` before generating new migrations
- Scope enforcement — every query must filter by scope; `tests/test_scope_enforcement.py` covers this
- Auth token validation — fail fast on `changeme` default (unless `KEI_ALLOW_INSECURE_DEFAULT_TOKEN=true`)
- Search indexing — smart search uses pre-computed aggregates; don't bypass the service layer

## Architecture Pointers
- `main.py` — app entrypoint, lifespan, router registration
- `routers/` — one file per resource type
- `dependencies.py` — auth dependency injection
- `config.py` — env var handling
- `docs/` — domain notes and API design decisions
- `CODEX_REVIEW_PROMPT.md` — review prompt used for prior code reviews (useful context)

## CLI Notes
- CLI lives at `cli/kei/` — separate installable package, tested independently
- CLI should always work against both local dev and deployed API
- Config stored by CLI: `~/.kei/config.json`
