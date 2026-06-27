# Kei API

Agent-first data API for scoped operational and financial records. The API is domain-agnostic: `scope` namespaces data, and `meta` JSON is the extension point for domain-specific fields.

## Current Shape

- API: FastAPI, SQLAlchemy, Alembic, SQLite
- CLI: installable Python package in `cli/kei/`
- Auth: bearer token with admin fallback plus scoped `agent_tokens`
- Default local port: `8081`
- Main resources: `entities`, `transactions`, `items`, `lists`, `services`, `snapshots`, `summary`, `audit`

## Documentation

Active docs live under `docs/`:

- [Docs index](docs/README.md)
- [API reference](docs/API.md)
- [Architecture notes](docs/ARCHITECTURE.md)
- [Deployment runbook](docs/DEPLOY.md)
- [CLI README](cli/kei/README.md)

Historical reviews, implementation plans, and stale design drafts are in `docs/archive/`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --port 8081 --reload
```

Set a real `KEI_API_TOKEN` for any non-local deployment. Startup fails if the token is left as `changeme` unless `KEI_ALLOW_INSECURE_DEFAULT_TOKEN=true`.

Docker:

```bash
docker compose up --build
```

Health check:

```bash
curl http://127.0.0.1:8081/health
```

## CLI

```bash
cd cli/kei
pip install -e .

export KEI_API_BASE=http://127.0.0.1:8081
export KEI_API_TOKEN=replace-with-long-random-token  # match the API .env
python -m kei.cli health
python -m kei.cli -s salon summary
```

CLI config is stored at `~/.config/kei/config.yaml`. Environment variables take precedence over config values.

## Auth And Scope

All `/api/*` endpoints require `Authorization: Bearer <token>`.

Token resolution:

1. SHA-256 hash lookup in `agent_tokens.token_hash`
2. Fallback to `KEI_API_TOKEN` as admin with `allowed_scopes=["*"]`

Every scoped resource has a `scope`. Create/update paths validate scopes against `KEI_VALID_SCOPES`; read paths filter by the caller's allowed scopes when the caller is not wildcard. Standard list endpoints can omit `scope`; wildcard tokens see all active rows, while scoped tokens see only their allowed scopes.

## Tests

Use the repo venv, never host-global Python:

```bash
.venv/bin/python -m pytest tests/ -q
```

The suite includes migration parity, auth, scope enforcement, validation, CRUD, summaries, external identity, and reconciliation coverage.
