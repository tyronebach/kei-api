"""Recurring income/expense rule commands."""

from datetime import date
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="recurring", help="Manage recurring income and expenses.")

_FREQ_HELP = "Frequency: monthly, weekly, biweekly, yearly, custom"


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


def _fmt_amount(rule: dict) -> str:
    amount = f"${rule.get('amount', 0):.2f}"
    return f"[red]-{amount}[/red]" if rule.get("type") == "expense" else f"[green]+{amount}[/green]"


def _print_rule(rule: dict) -> None:
    rprint(f"[bold]{rule.get('name')}[/bold] ([dim]{rule.get('id', '')[:8]}[/dim])")
    rprint(f"  Type:      {rule.get('type')}")
    rprint(f"  Amount:    {_fmt_amount(rule)}")
    rprint(f"  Category:  {rule.get('category')}")
    freq = rule.get("frequency")
    if rule.get("interval", 1) > 1:
        freq = f"every {rule['interval']} {freq}"
    if rule.get("day_of_month"):
        freq += f" (day {rule['day_of_month']})"
    rprint(f"  Frequency: {freq}")
    rprint(f"  Started:   {rule.get('start_date')}")
    if rule.get("end_date"):
        rprint(f"  Ends:      {rule.get('end_date')}")
    if rule.get("next_due"):
        rprint(f"  Next due:  [cyan]{rule.get('next_due')}[/cyan]")
    else:
        rprint("  Next due:  [dim]stopped[/dim]")
    if rule.get("description"):
        rprint(f"  Note:      {rule.get('description')}")


@app.command("add")
def add(
    ctx: typer.Context,
    type: str = typer.Argument(..., help="income or expense"),
    amount: float = typer.Argument(..., help="Amount"),
    category: str = typer.Argument(..., help="Category"),
    name: str = typer.Option(..., "--name", "-n", help="Rule name (e.g. 'Rent', 'Netflix')"),
    frequency: str = typer.Option("monthly", "--freq", "-f", help=_FREQ_HELP),
    start: Optional[str] = typer.Option(None, "--start", help="Start date YYYY-MM-DD (default: today)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date YYYY-MM-DD (optional)"),
    day: Optional[int] = typer.Option(None, "--day", help="Day of month for monthly rules (1-28)"),
    interval: int = typer.Option(1, "--interval", help="Every N units (e.g. 2 = bimonthly)"),
    desc: Optional[str] = typer.Option(None, "--desc", "-d", help="Description / notes"),
    entity: Optional[str] = typer.Option(None, "--entity", "-e", help="Linked entity ID/prefix"),
    cash: bool = typer.Option(False, "--cash", help="Cash payment method"),
    card: bool = typer.Option(False, "--card", help="Card payment method"),
):
    """Create a recurring income or expense rule.

    Examples:

      kei -s home recurring add expense 2000 housing --name Rent --day 1
      kei -s home recurring add income 1200 rental --name "Tenant rent" --day 1
      kei -s home recurring add expense 19.99 subscriptions --name Netflix --freq monthly
      kei -s home recurring add expense 3600 insurance --name "Car insurance" --freq yearly
    """
    if type not in ("income", "expense"):
        rprint("[red]Type must be 'income' or 'expense'[/red]")
        raise typer.Exit(1)

    client = get_client(ctx)
    data: dict = {
        "type": type,
        "amount": amount,
        "category": category,
        "name": name,
        "frequency": frequency,
        "interval": interval,
        "start_date": start or date.today().isoformat(),
    }
    if end:
        data["end_date"] = end
    if day:
        data["day_of_month"] = day
    if desc:
        data["description"] = desc
    if entity:
        data["entity_id"] = entity
    if cash:
        data["payment_method"] = "cash"
    elif card:
        data["payment_method"] = "card"

    result = client.recurring_create(**data)
    rule = result.get("data", result)
    rprint(f"[green]✓ Created recurring rule:[/green] {rule.get('name')} (ID: {rule.get('id', '')[:8]})")
    rprint(f"  Next due: [cyan]{rule.get('next_due', '-')}[/cyan]")


@app.command("list")
def list_rules(
    ctx: typer.Context,
    type: Optional[str] = typer.Option(None, "--type", "-t", help="income or expense"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    all: bool = typer.Option(False, "--all", "-a", help="Include stopped/expired rules"),
):
    """List recurring rules.

    Examples:

      kei -s home recurring list
      kei -s home recurring list --type expense
      kei -s home recurring list --all
    """
    client = get_client(ctx)
    params: dict = {"active_only": not all}
    if type:
        params["type"] = type
    if category:
        params["category"] = category

    result = client.recurring_list(**params)
    rules = result.get("data", [])

    if not rules:
        rprint("[yellow]No recurring rules found.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Amount", justify="right")
    table.add_column("Frequency")
    table.add_column("Next Due")
    table.add_column("Category")

    for r in rules:
        freq = r.get("frequency", "")
        if r.get("day_of_month"):
            freq += f" (d{r['day_of_month']})"
        next_due = r.get("next_due") or "[dim]stopped[/dim]"
        table.add_row(
            r.get("id", "")[:8],
            r.get("name", ""),
            r.get("type", ""),
            _fmt_amount(r),
            freq,
            next_due,
            r.get("category", ""),
        )

    rprint(table)
    rprint(f"[dim]{len(rules)} rule(s)[/dim]")


@app.command("get")
def get(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
):
    """Show details for a recurring rule."""
    client = get_client(ctx)
    result = client.recurring_get(rule_id)
    _print_rule(result.get("data", result))


@app.command("edit")
def edit(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    amount: Optional[float] = typer.Option(None, "--amount", "-a"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    frequency: Optional[str] = typer.Option(None, "--freq", "-f", help=_FREQ_HELP),
    day: Optional[int] = typer.Option(None, "--day"),
    desc: Optional[str] = typer.Option(None, "--desc", "-d"),
    end: Optional[str] = typer.Option(None, "--end", help="New end date YYYY-MM-DD"),
    from_date: Optional[str] = typer.Option(
        None, "--from",
        help="Apply changes from this date only (forks the rule). YYYY-MM-DD",
    ),
):
    """Edit a recurring rule.

    Without --from: edits in place (all unmodified future instances follow).
    With --from: closes the current rule and creates a new one from that date.

    Examples:

      kei -s home recurring edit abc123 --amount 2200
      kei -s home recurring edit abc123 --amount 2200 --from 2026-04-01
    """
    client = get_client(ctx)
    data: dict = {}
    if amount is not None:
        data["amount"] = amount
    if name:
        data["name"] = name
    if category:
        data["category"] = category
    if frequency:
        data["frequency"] = frequency
    if day is not None:
        data["day_of_month"] = day
    if desc:
        data["description"] = desc
    if end:
        data["end_date"] = end

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    result = client.recurring_update(rule_id, effective_from=from_date, **data)
    rule = result.get("data", result)
    if result.get("forked_from"):
        rprint(f"[green]✓ Forked rule from {from_date}:[/green] new ID {rule.get('id', '')[:8]}")
    else:
        rprint(f"[green]✓ Updated:[/green] {rule.get('name')}")
    _print_rule(rule)


@app.command("stop")
def stop(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    end_date: Optional[str] = typer.Option(None, "--date", help="Last date YYYY-MM-DD (default: today)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Stop a recurring rule.

    Example:

      kei -s home recurring stop abc123
      kei -s home recurring stop abc123 --date 2026-12-31
    """
    if not force:
        confirm = typer.confirm(f"Stop recurring rule {rule_id}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    result = client.recurring_stop(rule_id, end_date=end_date)
    rule = result.get("data", result)
    rprint(f"[green]✓ Stopped:[/green] {rule.get('name')} (ends {rule.get('end_date')})")


@app.command("skip")
def skip(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    skip_date: str = typer.Argument(..., help="Date to skip YYYY-MM-DD"),
):
    """Skip one occurrence of a recurring rule.

    Example:

      kei -s home recurring skip abc123 2026-03-01
    """
    client = get_client(ctx)
    result = client.recurring_skip(rule_id, skip_date)
    rprint(f"[green]✓ Skipped {skip_date}[/green] for rule {rule_id[:8]}")


@app.command("unskip")
def unskip(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    skip_date: str = typer.Argument(..., help="Date to restore YYYY-MM-DD"),
):
    """Restore a previously skipped occurrence."""
    client = get_client(ctx)
    client.recurring_unskip(rule_id, skip_date)
    rprint(f"[green]✓ Restored {skip_date}[/green] for rule {rule_id[:8]}")


@app.command("instances")
def instances(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    from_date: str = typer.Option(..., "--from", help="Start date YYYY-MM-DD"),
    to_date: str = typer.Option(..., "--to", help="End date YYYY-MM-DD"),
):
    """Show all occurrences of a rule in a date range.

    Example:

      kei -s home recurring instances abc123 --from 2026-01-01 --to 2026-12-31
    """
    client = get_client(ctx)
    result = client.recurring_instances(rule_id, from_date, to_date)
    items = result.get("data", [])

    if not items:
        rprint("[yellow]No instances in this range.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Date")
    table.add_column("Status")
    table.add_column("Amount", justify="right")
    table.add_column("Type")
    table.add_column("Category")
    table.add_column("Tx ID", style="dim")

    status_style = {"confirmed": "green", "projected": "dim", "skipped": "yellow"}
    for inst in items:
        status = inst.get("status", "")
        style = status_style.get(status, "")
        amount = f"${inst.get('amount', 0):.2f}"
        if inst.get("type") == "expense":
            amount = f"[red]-{amount}[/red]"
        else:
            amount = f"[green]+{amount}[/green]"
        table.add_row(
            inst.get("date", ""),
            f"[{style}]{status}[/{style}]",
            amount,
            inst.get("type", ""),
            inst.get("category", ""),
            (inst.get("transaction_id") or "")[:8],
        )

    rprint(table)
    rprint(f"[dim]{len(items)} instance(s)[/dim]")


@app.command("generate")
def generate(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    through: str = typer.Argument(..., help="Materialise through this date YYYY-MM-DD"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Materialise projected instances as real transaction rows.

    Skipped and already-confirmed instances are left untouched.

    Example:

      kei -s home recurring generate abc123 2026-12-31
    """
    if not force:
        confirm = typer.confirm(f"Materialise recurring instances through {through}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    result = client.recurring_generate(rule_id, through)
    data = result.get("data", {})
    count = data.get("created", 0)
    rprint(f"[green]✓ Created {count} transaction(s)[/green]")
    if data.get("dates"):
        for d in data["dates"]:
            rprint(f"  [dim]{d}[/dim]")


@app.command("delete")
def delete(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule ID or prefix"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a recurring rule (soft delete). Existing transactions are kept."""
    if not force:
        confirm = typer.confirm(f"Delete recurring rule {rule_id}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    client.recurring_delete(rule_id)
    rprint(f"[green]✓ Deleted rule {rule_id[:8]}[/green]")
