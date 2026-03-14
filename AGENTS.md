# AGENTS.md — Kei API + CLI

Agent-first data API for LLM assistants. Domain-agnostic via `scope` namespacing and `meta` JSON for domain-specific fields.

## Stack
- **API:** FastAPI + SQLAlchemy + Alembic + SQLite
- **CLI:** Python package at `cli/kei/`
- **Auth:** Bearer token (`KEI_API_TOKEN`)
- **Port:** 8081

## Test Execution (Non-Negotiable)
Use venv or Docker — never host-global Python.

```bash
# Preferred
.venv/bin/python -m pytest tests/ -q

# If venv missing
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Docker
docker compose exec api python -m pytest tests/ -q
```

## Dev Commands
```bash
# API
source .venv/bin/activate
alembic upgrade head
uvicorn main:app --port 8081 --reload

# Docker
docker compose up --build

# CLI
cd cli/kei && pip install -e .
export KEI_API_BASE=http://127.0.0.1:8081
export KEI_API_TOKEN=test-token
python -m kei.cli health
```

## Core Rules
- **Commit directly to `main`.** No branches.
- Conventional commits: `feat:` `fix:` `refactor:` `docs:` `test:`
- **Every schema change needs an Alembic migration.** Never evolve schema via `create_all()`.
- **Scope enforcement is sacred.** Every query filters by scope. Do not let scopes cross-contaminate.
- `meta` JSON is the extension point — new domain fields go there, not new columns.
- Run `alembic current` + `alembic heads` before generating any new migration.

## Hard-Cut Product Policy
- Optimize for one canonical current-state implementation.
- Do **not** preserve or add compatibility bridges, migration shims, silent fallbacks, compact adapters, or dual paths for historical local states unless explicitly requested.
- Prefer one canonical codepath, fail-fast diagnostics, and explicit recovery steps.
- If temporary transition code is unavoidable, document in the same diff: why it exists, why the canonical path is insufficient, exact deletion criteria, and the tracking ADR/task.
- Default stance: delete old-state compatibility code instead of carrying it forward.

## Resource Types
`entities` · `items` · `lists` · `transactions` · `services` · `summary`

## Key Files
| File | Purpose |
|---|---|
| `main.py` | App entrypoint + router registration |
| `routers/` | One file per resource type |
| `dependencies.py` | Auth dependency injection |
| `config.py` | Env var handling |
| `IMPLEMENTATION_PLAN.md` | Hardening roadmap — read before major work |
| `CODEX_REVIEW_PROMPT.md` | Prior review prompt (useful context) |

## High-Risk Areas
- Alembic migration chain
- Scope enforcement (`tests/test_scope_enforcement.py`)
- Auth token fail-fast on `changeme` default
- Search + pre-computed aggregates — don't bypass service layer

## CLI (cli/kei/)
Separate installable package. Test it independently of the API.
Config lives at `~/.kei/config.json`.
