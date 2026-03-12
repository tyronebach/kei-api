# Kei API Deployment Runbook

This runbook describes how to deploy and operate Kei API with Alembic migrations and scoped agent auth.

## Prerequisites

- Python 3.12+
- `sqlite3` available on host
- Docker + Docker Compose (for container deployment)

## Environment

Required variables:

| Variable | Example | Notes |
|---|---|---|
| `KEI_DATABASE_URL` | `sqlite:///./data/kei.db` | SQLite database URL |
| `KEI_API_TOKEN` | `changeme` | Legacy admin token fallback |
| `KEI_VALID_SCOPES` | `["home","salon","woodwards","synthhub"]` | JSON list; write scopes are validated against this |

Create `.env` from example:

```bash
cp .env.example .env
```

## Local Deployment

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

Expected: `{"status":"ok"}`.

## Docker Deployment

The container entrypoint runs migrations automatically before starting Uvicorn.

```bash
docker compose up -d --build
docker compose logs -f kei-api
```

Health check:

```bash
docker compose exec kei-api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8081/health').read().decode())"
```

## Migration Workflow

Create migration:

```bash
.venv/bin/alembic revision -m "describe_change"
```

Apply migrations:

```bash
.venv/bin/alembic upgrade head
```

Check current revision:

```bash
.venv/bin/alembic current
```

Rollback one revision:

```bash
.venv/bin/alembic downgrade -1
```

## Agent Token Provisioning

### How auth works

1. Request `Authorization: Bearer <token>` → SHA-256 hash → lookup in `agent_tokens.token_hash`
2. If matched: `created_by`/`updated_by` set to that agent's `agent_id`
3. If no match: fallback to legacy `KEI_API_TOKEN` env var → attributed as `admin`

### Token schema (`agent_tokens` table)

| Column | Purpose |
|--------|---------|
| `agent_id` | Unique agent name (e.g., `rem`, `satella`) |
| `token_hash` | SHA-256 of the raw token |
| `allowed_scopes` | JSON list of scopes the agent can access (e.g., `["home","salon","woodwards","synthhub"]`) |
| `permissions` | JSON list: `["read"]` or `["read","write"]` |

### Token file convention

Raw tokens are stored on disk (not in agent configs or SKILL.md files):

```
~/.config/kei/tokens/<agent_id>    # mode 0600
```

Agents read their token at runtime:
```bash
export KEI_API_TOKEN=$(cat ~/.config/kei/tokens/rem)
```

### Current tokens

| Agent | Scopes | Permissions |
|-------|--------|-------------|
| rem | home, salon, woodwards, synthhub | read, write |
| satella | home, salon, woodwards, synthhub | read |
| beatrice | home, salon, woodwards, synthhub | read, write |

### Provisioning a new token

```bash
.venv/bin/python - <<'PY'
import hashlib, secrets, time, os
from sqlalchemy import create_engine, text
from config import settings

agent_id = "new-agent"
allowed_scopes_json = '["home","salon","woodwards","synthhub"]'
permissions_json = '["read","write"]'

raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

engine = create_engine(settings.database_url)
with engine.begin() as conn:
    conn.execute(text("""
        DELETE FROM agent_tokens WHERE agent_id = :agent_id
    """), {"agent_id": agent_id})
    conn.execute(text("""
        INSERT INTO agent_tokens (id, agent_id, token_hash, allowed_scopes, permissions, created_at)
        VALUES (lower(hex(randomblob(16))), :agent_id, :token_hash, json(:allowed_scopes), json(:permissions), :created_at)
    """), {
        "agent_id": agent_id,
        "token_hash": token_hash,
        "allowed_scopes": allowed_scopes_json,
        "permissions": permissions_json,
        "created_at": int(time.time()),
    })

# Save raw token to disk
token_dir = os.path.expanduser("~/.config/kei/tokens")
os.makedirs(token_dir, mode=0o700, exist_ok=True)
token_file = os.path.join(token_dir, agent_id)
with open(token_file, "w") as f:
    f.write(raw_token)
os.chmod(token_file, 0o600)

print(f"Provisioned {agent_id} → {token_file}")
PY
```

## Backup and Restore (SQLite, WAL-safe)

### Backup

Use SQLite online backup API (preferred over raw file copy):

```bash
mkdir -p backups
sqlite3 data/kei.db ".backup 'backups/kei-$(date +%F-%H%M%S).db'"
```

### Restore

1. Stop API
2. Replace DB file with backup
3. Start API
4. Run health check

```bash
docker compose stop kei-api
cp backups/kei-YYYY-MM-DD-HHMMSS.db data/kei.db
docker compose up -d kei-api
curl -sS http://127.0.0.1:8081/health
```

## Release Checklist

1. Run tests: `.venv/bin/pytest -q`
2. Apply migrations: `.venv/bin/alembic upgrade head`
3. Verify revision: `.venv/bin/alembic current`
4. Verify health endpoint
5. Validate one auth-protected API call with a real token

## Rollback Plan

1. Stop service
2. Restore latest known-good DB backup
3. Start service
4. Verify `/health`
5. Re-test core APIs (`/api/transactions`, `/api/summary`, `/api/entities`)
