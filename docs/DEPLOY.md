# Kei API Deployment Runbook

This runbook covers local operation, Docker operation, migrations, token provisioning, backups, and release checks for the current repo.

## Prerequisites

- Python 3.12+
- SQLite tooling available on the host for backup/restore
- Docker and Docker Compose for container operation

## Environment

Copy the example file and set a real token:

```bash
cp .env.example .env
```

Important variables:

| Variable | Example | Notes |
|---|---|---|
| `KEI_DATABASE_URL` | `sqlite:///./data/kei.db` | SQLite URL |
| `KEI_API_TOKEN` | long random string | Admin fallback token; do not leave as `changeme` outside local-only testing |
| `KEI_VALID_SCOPES` | `["home","salon","woodwards","synthhub","household"]` | JSON list of accepted write scopes |
| `KEI_CORS_ORIGINS` | `["http://localhost:5173"]` | Browser allowlist, empty by default |
| `KEI_ALLOW_INSECURE_DEFAULT_TOKEN` | `false` | Local-only escape hatch for `changeme` |

Startup fails when `KEI_API_TOKEN=changeme` unless `KEI_ALLOW_INSECURE_DEFAULT_TOKEN=true`.

## Local Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8081
```

Health check:

```bash
curl -sS http://127.0.0.1:8081/health
```

Expected:

```json
{"status":"ok"}
```

## Docker Run

The container entrypoint runs `alembic upgrade head` before starting Uvicorn.

```bash
docker compose up -d --build
docker compose logs -f kei-api
```

Health check from the container:

```bash
docker compose exec kei-api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8081/health').read().decode())"
```

## Migration Workflow

Before generating a migration:

```bash
.venv/bin/alembic current
.venv/bin/alembic heads
```

Create a migration:

```bash
.venv/bin/alembic revision -m "describe_change"
```

Apply migrations:

```bash
.venv/bin/alembic upgrade head
```

Rollback one revision:

```bash
.venv/bin/alembic downgrade -1
```

Schema changes must use Alembic. Do not evolve runtime schema with `Base.metadata.create_all()`.

## Agent Token Provisioning

Auth checks the SHA-256 hash of the bearer token against `agent_tokens.token_hash`. If no row matches, it falls back to the `KEI_API_TOKEN` admin token.

`agent_tokens` columns:

| Column | Purpose |
|---|---|
| `agent_id` | Stable agent name for attribution |
| `token_hash` | SHA-256 hash of the raw bearer token |
| `allowed_scopes` | JSON list, for example `["home","salon"]` or `["*"]` |
| `permissions` | JSON list, usually `["read"]` or `["read","write"]` |

Recommended local token file convention:

```text
~/.config/kei/tokens/<agent_id>
```

Provision or rotate a token:

```bash
.venv/bin/python - <<'PY'
import hashlib
import os
import secrets
import time

from sqlalchemy import create_engine, text

from config import settings

agent_id = "agent-name"
allowed_scopes_json = '["home","salon"]'
permissions_json = '["read","write"]'

raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

engine = create_engine(settings.database_url)
with engine.begin() as conn:
    conn.execute(
        text("DELETE FROM agent_tokens WHERE agent_id = :agent_id"),
        {"agent_id": agent_id},
    )
    conn.execute(
        text("""
            INSERT INTO agent_tokens
                (id, agent_id, token_hash, allowed_scopes, permissions, created_at)
            VALUES
                (lower(hex(randomblob(16))), :agent_id, :token_hash,
                 json(:allowed_scopes), json(:permissions), :created_at)
        """),
        {
            "agent_id": agent_id,
            "token_hash": token_hash,
            "allowed_scopes": allowed_scopes_json,
            "permissions": permissions_json,
            "created_at": int(time.time()),
        },
    )

token_dir = os.path.expanduser("~/.config/kei/tokens")
os.makedirs(token_dir, mode=0o700, exist_ok=True)
token_file = os.path.join(token_dir, agent_id)
with open(token_file, "w", encoding="utf-8") as f:
    f.write(raw_token)
os.chmod(token_file, 0o600)

print(f"Provisioned {agent_id}: {token_file}")
PY
```

Use it:

```bash
export KEI_API_TOKEN="$(cat ~/.config/kei/tokens/agent-name)"
```

## Backup And Restore

Use SQLite's online backup API rather than raw file copying while the service may be running.

Backup:

```bash
mkdir -p backups
sqlite3 data/kei.db ".backup 'backups/kei-$(date +%F-%H%M%S).db'"
```

Restore:

```bash
docker compose stop kei-api
cp backups/kei-YYYY-MM-DD-HHMMSS.db data/kei.db
docker compose up -d kei-api
curl -sS http://127.0.0.1:8081/health
```

## Release Checklist

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic heads
curl -sS http://127.0.0.1:8081/health
```

Then validate one authenticated read and one authenticated write with the token expected to be used by the deployed agent.

## Rollback

1. Stop the service.
2. Restore the latest known-good SQLite backup.
3. Start the service.
4. Verify `/health`.
5. Re-test the core endpoints needed by the deployed agents.
