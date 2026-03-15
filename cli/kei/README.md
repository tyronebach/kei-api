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

Canonical scopes:
- `home`
- `salon`
- `woodwards`
- `synthhub`

Configure via `KEI_VALID_SCOPES=["home","salon","woodwards","synthhub"]`.

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

# Add income with explicit payment method
kei tx add income 85 haircut --payment-method etransfer
# Valid payment methods: cash, etransfer, card, bank, cheque, other
# Note: --cash and --card are convenience shortcuts for --payment-method cash/card
# --payment-method takes precedence over --cash/--card if both are provided

# Add expense
kei tx add expense 50 supplies --desc "Shampoo order"

# List transactions
kei tx list --type income --from 2026-02-01

# Filter by payment method or source
kei tx list --payment-method cash
kei tx list --payment-method etransfer --from 2026-01-01
kei tx list --external-source tributary       # bank-feed transactions only

# List as JSON (for scripting / agent use)
kei tx list --format json
kei tx list -f json --type expense

# Fix a mistake (full update — send all fields to change)
kei tx update <id> --amount 58
kei tx update <id> --category dining --desc "corrected vendor"
kei tx update <id> --entity <entity-id>    # link an entity
kei tx update <id> --entity "kevin"        # name prefix resolves automatically

# Link an entity (partial update — only entity_id touched)
kei tx link <id> "michelle"               # name prefix resolves automatically
kei tx link <id> <full-entity-id>

# Delete (interactive confirmation)
kei tx delete <id>

# Delete without prompt (scripting)
kei tx delete <id> -y
kei tx delete <id> --yes
kei tx delete <id> --force
```

#### Duplicate detection

The API runs fuzzy dedup on manual writes (amount + description + date proximity).

- **Hard block (score ≥ 92):** transaction is **not** recorded:
  ```
  ⚠ Skipped: duplicate transaction detected (ID: 3c1a6a27, date: 2026-03-14, amount: $80.00, category: haircut). Use --force to override.
  ```
- **Warn band (score 60–91):** transaction **is** recorded, but CLI warns:
  ```
  ⚠ Note: possible duplicate (ID: 3c1a6a27, score: 78/100). Transaction was recorded.
  ```
- **Reconciled (Tributary path):** if Tributary already synced this transaction, your entry attaches to the existing row instead of creating a duplicate:
  ```
  ↔ Reconciled: matched existing row 3c1a6a27 (entity: none)
  ```
- **Enriched (Rem path):** if Rem adds description/entity to a Tributary row:
  ```
  ↔ Enriched: updated Tributary row 3c1a6a27 with your description/entity
  ```
- **Force bypass:** pass `--force` to skip dedup entirely and always create a new record:
  ```bash
  kei tx add income 85 haircut --entity <id> --force
  ```

#### `tx link` vs `tx update --entity`

| Command | Use when |
|---------|----------|
| `kei tx link <id> <entity>` | Only linking an entity — nothing else changes. Uses PATCH, minimal footprint. |
| `kei tx update <id> --entity <e> --amount 90` | Changing multiple fields at once. Uses PUT. |

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

# Filter by source (bank = Tributary-pushed, cash = cash-only, agent = manual non-cash)
kei summary --source bank
kei summary --source cash
kei -s salon summary --source bank --period year

# Compare to previous period
kei summary trends --period month
kei summary trends --source bank    # bank-verified trend only

# Busiest days
kei summary by-day

# Cross-scope breakdown
kei summary by-scope

# Monthly P&L (last 12 months by default)
kei summary by-month
kei -s salon summary by-month --from 2025-01-01 --to 2025-12-31
kei summary by-month --source bank        # bank-verified income/expenses only
kei summary by-month --source cash        # cash transactions only
kei summary by-month -f json              # machine-readable
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
| `tx get` | `GET /api/transactions/{id}` |
| `tx update` | `PUT /api/transactions/{id}` |
| `tx link` | `PATCH /api/transactions/{id}` |
| `tx delete` | `DELETE /api/transactions/{id}` |
| `item low-stock` | `GET /api/items/low-stock` |
| `list show` | `GET /api/lists/items?list=...` |
| `list add` | `POST /api/lists/items` |
| `summary` | `GET /api/summary` |
| `summary trends` | `GET /api/summary/trends` |
| `summary by-day` | `GET /api/summary/by-day` |
| `summary by-scope` | `GET /api/summary/by-scope` |
| `summary by-month` | `GET /api/summary/by-month` |
