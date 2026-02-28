# Kei CLI (経)

Agent-first data management CLI for LLM assistants. Wraps the Kei API with simple, scope-aware commands.

## Installation

```bash
cd ~/Projects/cli/kei
pip install -e .
```

Or with pipx for isolated install:

```bash
pipx install ~/Projects/cli/kei
```

## Configuration

```bash
# Set API endpoint and token
kei config --api-base http://localhost:8081 --token your-secret

# Set default scope (optional)
kei config --default-scope home

# View config
kei config --show
```

Or use environment variables:
- `KEI_API_BASE` - API base URL
- `KEI_API_TOKEN` - Bearer token
- `KEI_SCOPE` - Default scope

## Scope Standard (Household)

Canonical scopes going forward:
- `home`
- `salon`
- `synthhub` (Thai side business)

API must allow all three via `KEI_VALID_SCOPES`.

### Per-Agent Tokens

Each agent has its own token for attribution (`created_by`/`updated_by` tracking).
Tokens are stored at `~/.config/kei/tokens/<agent_id>` and loaded at runtime:

```bash
export KEI_API_TOKEN=$(cat ~/.config/kei/tokens/rem)
kei -s salon entity search "kevin"
```

See [kei-api DEPLOY.md](../kei-api/DEPLOY.md#agent-token-provisioning) for provisioning.

### Recommended Agent Scope Policies

- **Rem**: read/write for `home` + `salon`
- **Minerva**: read/write for `synthhub`
- **Anastasia**: read-only for `home` + `salon` + `synthhub`

Example target policies at token provision time:
- Minerva → `allowed_scopes=["synthhub"]`, `permissions=["read","write"]`
- Anastasia → `allowed_scopes=["home","salon","synthhub"]`, `permissions=["read"]`

## Usage

### Scope

Every command can take `--scope` / `-s` to namespace data:

```bash
kei -s salon entity search "kevin"
kei -s home list show shopping
kei -s synthhub tx list --type expense
```

Or set a default scope in config/env.

Write commands require scope (`entity add`, `tx add`, `item add`, `service add`, `list add`, `list clear`).

---

## Commands

### Entities (clients, people, businesses)

```bash
# Add a client
kei entity add "Kevin Lai" --type client --phone "444-555-6666"

# Search (typo-tolerant)
kei entity search "keven"    # finds "Kevin"

# Get entity details
kei entity get <id>

# Get activity/profile (visit history, spending)
kei entity activity <id>

# Update
kei entity update <id> --phone "555-9999"

# Find inactive clients
kei entity insights --inactive-days 30

# Top spenders
kei entity insights --min-visits 5 --sort total_spend
```

### Transactions (income/expenses)

```bash
# Add income
kei tx add income 85 haircut --entity <id> --cash

# Add expense
kei tx add expense 50 supplies --desc "Shampoo order"

# List transactions
kei tx list --type income --from 2026-02-01

# Fix a mistake
kei tx update <id> --amount 58

# Delete
kei tx delete <id>
```

### Items (inventory)

```bash
# Add item
kei item add "Purple Shampoo 500ml" --category haircare --qty 12 --reorder 5

# Search inventory
kei item search "shampoo"

# Check low stock
kei item low-stock

# Restock
kei item adjust <id> --in 10 --reason "Restocked from supplier"

# Use inventory
kei item adjust <id> --out 2 --reason "Used for client"

# View movement history
kei item movements <id>
```

### Services (catalog)

```bash
# Add service
kei service add "Balayage" 180 --category color --duration 120 --tags premium

# List/filter services
kei service list
kei service list --category color
kei service list --tag premium

# Update / delete
kei service update <id> --price 190
kei service delete <id>
```

### Lists (shopping, todo, etc.)

```bash
# Show list names
kei list names

# Show shopping list (unchecked items)
kei list show shopping

# Add to list
kei list add shopping "eggs"
kei list add todo "Call landlord"

# Check off item
kei list check <id>

# Remove item
kei list remove <id>

# Clear checked items
kei list clear shopping --checked-only
```

### Summary (analytics)

```bash
# This month's overview
kei summary

# Specific period
kei summary --period week
kei summary --period custom --from 2026-01-01 --to 2026-01-31

# Compare to previous period
kei summary trends --period month

# Busiest days
kei summary by-day

# Cross-scope breakdown
kei summary by-scope
```

---

## For Agents (Rem, Minerva)

### Rem's Home Commands

```bash
# Shopping list
kei -s home list add shopping "eggs"
kei -s home list show shopping
kei -s home list check <id>

# Todo list
kei -s home list add todo "Call plumber"
kei -s home list show todo

# Home expenses
kei -s home tx add expense 87 dining --desc "Date night dinner"
```

### Rem's Salon Commands

```bash
# Client lookup
kei -s salon entity search "kevin"
kei -s salon entity activity <id>

# Record payment
kei -s salon tx add income 85 haircut --entity <id> --cash

# Inventory
kei -s salon item low-stock
kei -s salon item adjust <id> --in 10

# Business summary
kei -s salon summary
kei -s salon summary trends
```

### Shell Aliases (optional)

Add to Rem's SKILL.md or shell config:

```bash
alias rem-home="kei -s home"
alias rem-salon="kei -s salon"

# Then:
rem-home list add shopping "milk"
rem-salon entity search "kevin"
```

---

## API Reference

Kei CLI wraps the [Kei API](../kei-api/README.md). All commands map to REST endpoints:

| Command | Endpoint |
|---------|----------|
| `entity add` | `POST /api/entities` |
| `entity search` | `GET /api/entities?search=...` |
| `entity activity` | `GET /api/entities/{id}/activity` |
| `tx add` | `POST /api/transactions` |
| `tx list` | `GET /api/transactions` |
| `item low-stock` | `GET /api/items/low-stock` |
| `list show` | `GET /api/lists/items?list=...` |
| `list add` | `POST /api/lists/items` |
| `summary` | `GET /api/summary` |
| `summary by-scope` | `GET /api/summary/by-scope` |
