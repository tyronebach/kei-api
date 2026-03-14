"""Transaction commands."""

import json
from datetime import date
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient
from .utils import resolve_id

app = typer.Typer(name="tx", help="Manage transactions (income/expenses).")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


@app.command("add")
def add(
    ctx: typer.Context,
    type: str = typer.Argument(..., help="Transaction type: income or expense"),
    amount: float = typer.Argument(..., help="Amount"),
    category: str = typer.Argument(..., help="Category (haircut, supplies, etc.)"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
    entity: Optional[str] = typer.Option(None, "--entity", "-e", help="Linked entity ID"),
    tx_date: Optional[str] = typer.Option(None, "--date", help="Date (YYYY-MM-DD), defaults to today"),
    cash: bool = typer.Option(False, "--cash", help="Cash payment"),
    card: bool = typer.Option(False, "--card", help="Card payment"),
    payment_method: Optional[str] = typer.Option(
        None,
        "--payment-method",
        help="Payment method: cash, etransfer, card, bank, cheque, other",
    ),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    force: bool = typer.Option(False, "--force", help="Bypass duplicate detection and force create"),
):
    """Add a transaction."""
    if type not in ("income", "expense"):
        rprint("[red]Type must be 'income' or 'expense'[/red]")
        raise typer.Exit(1)

    client = get_client(ctx)
    resolved_date = tx_date or date.today().isoformat()
    data = {
        "type": type,
        "amount": amount,
        "category": category,
        "date": resolved_date,
    }
    if description:
        data["description"] = description
    if entity:
        if len(entity) < 32:
            all_entities = client.entity_list(limit=200).get("data", [])
            entity = resolve_id(all_entities, entity)
            if not entity:
                raise typer.Exit(1)
        data["entity_id"] = entity
    valid_payment_methods = {"cash", "etransfer", "card", "bank", "cheque", "other"}
    if payment_method:
        if payment_method not in valid_payment_methods:
            rprint(f"[red]Invalid payment method '{payment_method}'. Valid: {', '.join(sorted(valid_payment_methods))}[/red]")
            raise typer.Exit(1)
        data["payment_method"] = payment_method
    elif cash:
        data["payment_method"] = "cash"
    elif card:
        data["payment_method"] = "card"
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]
    if force:
        data["force_create"] = True

    result = client.tx_create(**data)

    # Duplicate detected — skipped, not recorded
    if result.get("matched"):
        dup = result.get("data", {})
        dup_id = (dup.get("id") or "")[:8]
        dup_date = dup.get("date", "")
        dup_amount = dup.get("amount", 0)
        dup_cat = dup.get("category", "")
        rprint(
            f"[yellow]⚠ Skipped: duplicate transaction detected "
            f"(ID: {dup_id}, date: {dup_date}, amount: ${dup_amount:.2f}, category: {dup_cat}). "
            f"Use --force to override.[/yellow]"
        )
        return

    # Recorded, but a probable duplicate exists
    if result.get("probable_match"):
        pm = result.get("probable_match", {})
        pm_id = (pm.get("id") or "")[:8]
        pm_score = result.get("match_score", 0)
        rprint(
            f"[yellow]⚠ Note: possible duplicate "
            f"(ID: {pm_id}, score: {pm_score}/100). Transaction was recorded.[/yellow]"
        )
        # Fall through to success message (transaction was created, but data key is absent here)
        # Build a synthetic display from the input values
        entity_suffix = f", entity: {entity[:8]}" if entity else ""
        rprint(
            f"[green]✓ Recorded {type}:[/green] "
            f"${amount:.2f} for {category} (date: {resolved_date}{entity_suffix})"
        )
        return

    # Normal success
    tx = result.get("data", result)
    tx_id = (tx.get("id") or "")[:8]
    tx_display_date = tx.get("date", resolved_date)
    entity_suffix = f", entity: {entity[:8]}" if entity else ""
    rprint(
        f"[green]✓ Recorded {type}:[/green] "
        f"${amount:.2f} for {category} "
        f"(ID: {tx_id}, date: {tx_display_date}{entity_suffix})"
    )


@app.command("list")
def list_tx(
    ctx: typer.Context,
    type: Optional[str] = typer.Option(None, "--type", "-t", help="income or expense"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    entity: Optional[str] = typer.Option(None, "--entity", "-e", help="Filter by entity ID"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List transactions."""
    client = get_client(ctx)
    params = {"limit": limit}
    if type:
        params["type"] = type
    if category:
        params["category"] = category
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if entity:
        params["entity_id"] = entity

    result = client.tx_list(**params)
    transactions = result.get("data", [])

    if not transactions:
        rprint("[yellow]No transactions found.[/yellow]")
        return

    if format == "json":
        print(json.dumps(transactions, indent=2))
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Category")
    table.add_column("Amount", justify="right")
    table.add_column("Description")

    for tx in transactions:
        amount_str = f"${tx.get('amount', 0):.2f}"
        if tx.get("type") == "expense":
            amount_str = f"[red]-{amount_str}[/red]"
        else:
            amount_str = f"[green]+{amount_str}[/green]"

        table.add_row(
            tx.get("id", "")[:8],
            tx.get("date", ""),
            tx.get("type", ""),
            tx.get("category", ""),
            amount_str,
            (tx.get("description", "") or "")[:30],
        )

    rprint(table)


@app.command("get")
def get(
    ctx: typer.Context,
    tx_id: str = typer.Argument(..., help="Transaction ID"),
):
    """Get transaction details."""
    client = get_client(ctx)
    result = client.tx_get(tx_id)
    tx = result.get("data", result)

    rprint(f"[bold]Transaction {tx.get('id', '')[:8]}[/bold]")
    rprint(f"  Type: {tx.get('type')}")
    rprint(f"  Amount: ${tx.get('amount', 0):.2f}")
    rprint(f"  Category: {tx.get('category')}")
    rprint(f"  Date: {tx.get('date')}")
    if tx.get("description"):
        rprint(f"  Description: {tx.get('description')}")
    if tx.get("entity_id"):
        rprint(f"  Entity: {tx.get('entity_id')}")
    if tx.get("payment_method"):
        rprint(f"  Payment: {tx.get('payment_method')}")


@app.command("update")
def update(
    ctx: typer.Context,
    tx_id: str = typer.Argument(..., help="Transaction ID"),
    amount: Optional[float] = typer.Option(None, "--amount", "-a", help="New amount"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="New category"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="New description"),
    tx_date: Optional[str] = typer.Option(None, "--date", help="New date"),
):
    """Update a transaction."""
    client = get_client(ctx)
    data = {}
    if amount is not None:
        data["amount"] = amount
    if category:
        data["category"] = category
    if description:
        data["description"] = description
    if tx_date:
        data["date"] = tx_date

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    client.tx_update(tx_id, **data)
    rprint(f"[green]Updated transaction {tx_id[:8]}[/green]")


@app.command("delete")
def delete(
    ctx: typer.Context,
    tx_id: str = typer.Argument(..., help="Transaction ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a transaction."""
    if not (force or yes):
        confirm = typer.confirm(f"Delete transaction {tx_id}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    client.tx_delete(tx_id)
    rprint(f"[green]Deleted transaction {tx_id[:8]}[/green]")
