"""Summary commands."""

from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="summary", help="Financial summaries and analytics.")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


def build_period_params(period: str, from_date: Optional[str], to_date: Optional[str]) -> dict:
    """Build period query params, validating custom range."""
    params = {"period": period}
    if period == "custom":
        if not from_date or not to_date:
            rprint("[red]Custom period requires --from and --to dates[/red]")
            raise typer.Exit(1)
        params["from"] = from_date
        params["to"] = to_date
    return params


@app.callback(invoke_without_command=True)
def overview(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="today, week, month, year, custom"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
):
    """Show summary overview (default: this month)."""
    if ctx.invoked_subcommand is not None:
        return

    client = get_client(ctx)
    params = build_period_params(period, from_date, to_date)

    result = client.summary(**params)
    data = result.get("data", result)

    period_info = data.get("period", {})
    rprint(f"[bold]Summary: {period_info.get('from', '')} to {period_info.get('to', '')}[/bold]")
    rprint()

    income = data.get("income", {})
    expenses = data.get("expenses", {})
    profit = data.get("profit", 0)

    rprint(f"  [green]Income:[/green]   ${income.get('total', 0):,.2f} ({income.get('count', 0)} transactions)")
    rprint(f"  [red]Expenses:[/red] ${expenses.get('total', 0):,.2f} ({expenses.get('count', 0)} transactions)")
    rprint(f"  [bold]Profit:[/bold]   ${profit:,.2f}")

    # Top categories
    if data.get("top_income"):
        rprint("\n[bold]Top Income:[/bold]")
        for cat in data["top_income"][:3]:
            rprint(f"  • {cat.get('category')}: ${cat.get('total', 0):,.2f} ({cat.get('count', 0)})")

    if data.get("top_expenses"):
        rprint("\n[bold]Top Expenses:[/bold]")
        for cat in data["top_expenses"][:3]:
            rprint(f"  • {cat.get('category')}: ${cat.get('total', 0):,.2f} ({cat.get('count', 0)})")

    # Client stats
    clients = data.get("clients", {})
    if clients:
        rprint(f"\n[bold]Clients:[/bold] {clients.get('active', 0)} active ({clients.get('new', 0)} new, {clients.get('returning', 0)} returning)")

    # Alerts
    if data.get("inventory_alerts"):
        rprint(f"\n[yellow]⚠ {data.get('inventory_alerts')} item(s) low on stock[/yellow]")


@app.command("trends")
def trends(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="Compare current vs previous period"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
):
    """Compare current period to previous."""
    client = get_client(ctx)
    params = build_period_params(period, from_date, to_date)
    result = client.summary_trends(**params)
    data = result.get("data", result)

    current = data.get("current", {})
    previous = data.get("previous", {})
    change = data.get("change", {})
    trend = data.get("trend", "stable")

    trend_emoji = {"up": "📈", "down": "📉", "stable": "➡️"}.get(trend, "")

    rprint(f"[bold]Trends ({period}) {trend_emoji}[/bold]")
    rprint()

    # Income
    inc_change = change.get("income", {})
    inc_pct = inc_change.get("percent", 0)
    inc_color = "green" if inc_pct >= 0 else "red"
    rprint(f"  Income:   ${current.get('income', 0):,.2f} vs ${previous.get('income', 0):,.2f}")
    rprint(f"            [{inc_color}]{inc_pct:+.1f}%[/{inc_color}] (${inc_change.get('amount', 0):+,.2f})")

    # Expenses
    exp_change = change.get("expenses", {})
    exp_pct = exp_change.get("percent", 0)
    exp_color = "green" if exp_pct <= 0 else "red"  # Lower expenses = good
    rprint(f"  Expenses: ${current.get('expenses', 0):,.2f} vs ${previous.get('expenses', 0):,.2f}")
    rprint(f"            [{exp_color}]{exp_pct:+.1f}%[/{exp_color}] (${exp_change.get('amount', 0):+,.2f})")

    # Profit
    prof_change = change.get("profit", {})
    prof_pct = prof_change.get("percent", 0)
    prof_color = "green" if prof_pct >= 0 else "red"
    rprint(f"  Profit:   ${current.get('profit', 0):,.2f} vs ${previous.get('profit', 0):,.2f}")
    rprint(f"            [{prof_color}]{prof_pct:+.1f}%[/{prof_color}] (${prof_change.get('amount', 0):+,.2f})")


@app.command("by-day")
def by_day(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="Period to analyze"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
):
    """Show income breakdown by day of week."""
    client = get_client(ctx)
    params = build_period_params(period, from_date, to_date)
    result = client.summary_by_day(**params)
    data = result.get("data", result)

    days = data.get("days", [])
    busiest = data.get("busiest", "")

    rprint(f"[bold]Income by Day ({period})[/bold]")
    rprint()

    table = Table(show_header=True)
    table.add_column("Day")
    table.add_column("Income", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("")

    for day in days:
        day_name = day.get("day", "")
        marker = "🌟" if day_name == busiest else ""
        table.add_row(
            day_name,
            f"${day.get('total', 0):,.2f}",
            str(day.get("count", 0)),
            marker,
        )

    rprint(table)
    if busiest:
        rprint(f"\n[bold]Busiest day:[/bold] {busiest}")


@app.command("by-scope")
def by_scope(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="Period to analyze"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
):
    """Show income/expense/profit grouped by scope."""
    client = get_client(ctx)
    params = build_period_params(period, from_date, to_date)
    result = client.summary_by_scope(**params)
    data = result.get("data", result)
    scopes = data.get("scopes", [])
    period_info = data.get("period", {})

    rprint(f"[bold]By Scope: {period_info.get('from', '')} to {period_info.get('to', '')}[/bold]")
    rprint()

    if not scopes:
        rprint("[yellow]No data for selected period.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Scope")
    table.add_column("Income", justify="right")
    table.add_column("Expenses", justify="right")
    table.add_column("Profit", justify="right")

    for row in scopes:
        income = row.get("income", {}).get("total", 0)
        expenses = row.get("expenses", {}).get("total", 0)
        profit = row.get("profit", 0)
        table.add_row(
            row.get("scope", ""),
            f"${income:,.2f}",
            f"${expenses:,.2f}",
            f"${profit:,.2f}",
        )

    rprint(table)
