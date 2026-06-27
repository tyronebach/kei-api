# Kei CLI

Typer CLI for Kei API. It wraps the HTTP API with scope-aware commands for agents and scripts.

## Install

From the repo root:

```bash
cd cli/kei
pip install -e .
```

Or install from the package directory with `pipx`:

```bash
pipx install ./cli/kei
```

## Configure

Environment variables take precedence:

```bash
export KEI_API_BASE=http://127.0.0.1:8081
export KEI_API_TOKEN=replace-with-long-random-token  # match the API .env
export KEI_SCOPE=home
```

Config file fallback:

```bash
kei config --api-base http://127.0.0.1:8081 --token replace-with-long-random-token
kei config --default-scope home
kei config --show
```

Config is stored at `~/.config/kei/config.yaml`.

For agent-token provisioning, see [the deployment runbook](../../docs/DEPLOY.md#agent-token-provisioning).

## Scope

Most write commands require a scope. Pass one explicitly:

```bash
kei -s salon entity search "kevin"
kei -s home list show shopping
kei -s synthhub tx list --type expense
```

Or set `KEI_SCOPE` / `default_scope`.

## Commands

### Health

```bash
kei health
```

### Entities

```bash
kei -s salon entity add "Kevin Lai" --type client --phone "444-555-6666"
kei -s salon entity search "keven"
kei -s salon entity get <id>
kei -s salon entity activity <id>
kei -s salon entity update <id> --phone "555-9999"
kei -s salon entity insights --inactive-days 30
```

### Transactions

```bash
kei -s salon tx add income 85 haircut --entity <entity-id> --cash
kei -s home tx add expense 50 supplies --desc "Shampoo order"
kei -s home tx list --from 2026-01-01 --payment-method cash
kei -s home tx list --external-source tributary
kei -s home tx get <id>
kei -s home tx update <id> --amount 58 --category dining
kei -s home tx link <id> <entity-id-or-name-prefix>
kei -s home tx delete <id> --yes
```

Valid payment methods: `cash`, `etransfer`, `card`, `bank`, `cheque`, `other`.

Manual transaction writes use the API's duplicate detection. Use `--force` only when a duplicate warning or block is expected and the new row is intentional.

### Items

```bash
kei -s salon item add "Purple Shampoo 500ml" --category haircare --qty 12 --reorder 5
kei -s salon item search "shampoo"
kei -s salon item low-stock
kei -s salon item adjust <id> --in 10 --reason "Restocked"
kei -s salon item adjust <id> --out 2 --reason "Used"
kei -s salon item movements <id>
```

### Services

```bash
kei -s salon service add "Balayage" 180 --category color --duration 120 --tags premium
kei -s salon service list
kei -s salon service list --category color
kei -s salon service update <id> --price 190
kei -s salon service delete <id>
```

### Lists

```bash
kei -s home list names
kei -s home list show shopping
kei -s home list add shopping "eggs"
kei -s home list check <id>
kei -s home list remove <id>
kei -s home list clear shopping --checked-only
```

### Summary

```bash
kei -s home summary
kei summary --period custom --from 2026-01-01 --to 2026-01-31
kei summary trends --period month
kei summary by-day --scope salon
kei summary by-scope
kei summary by-category --type expense
kei summary by-month --source bank
kei summary pulse
```

Scope behavior is command-specific:

- `summary`, `trends`, and `by-day` respect the global `-s/--scope` value unless an endpoint-specific `--scope` overrides it.
- `by-scope`, `by-month`, `by-category`, and `pulse` are intended for cross-scope views unless `--scope` is passed.

### Snapshots

```bash
kei snapshot
kei snapshot list
kei snapshot show 2026-03-20
kei snapshot diff 2026-03-17
kei snapshot diff 2026-03-17 2026-03-25
kei snapshot --format json
```

Snapshots default to `scope=household`.

## Endpoint Map

| Command | Endpoint |
|---|---|
| `entity add/search/get/activity/update` | `/api/entities` |
| `tx add/list/get/update/link/delete` | `/api/transactions` |
| `item add/search/low-stock/adjust/movements` | `/api/items` |
| `service add/list/update/delete` | `/api/services` |
| `list names/show/add/check/remove/clear` | `/api/lists` |
| `summary ...` | `/api/summary` |
| `snapshot ...` | `/api/snapshots` |
