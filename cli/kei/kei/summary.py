"""Summary commands."""

from datetime import date
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="summary", help="Financial summaries and analytics.")


def get_client(ctx: typer.Context) -> KeiClient:
    """Get client with the global scope (for overview command)."""
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


def get_scoped_client(ctx: typer.Context, scope: str | None, default_all: bool = False) -> KeiClient:
    """Get client with explicit scope control for summary subcommands."""
    if scope and scope.lower() == "all":
        return KeiClient(scope=None)
    if scope:
        return KeiClient(scope=scope)
    if default_all:
        return KeiClient(scope=None)
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
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
):
    """Show summary overview (default: this month)."""
    if ctx.invoked_subcommand is not None:
        return

    client = get_client(ctx)
    params = build_period_params(period, from_date, to_date)
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method

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

    if data.get("top_income"):
        rprint("\n[bold]Top Income:[/bold]")
        for cat in data["top_income"][:3]:
            rprint(f"  • {cat.get('category')}: ${cat.get('total', 0):,.2f} ({cat.get('count', 0)})")

    if data.get("top_expenses"):
        rprint("\n[bold]Top Expenses:[/bold]")
        for cat in data["top_expenses"][:3]:
            rprint(f"  • {cat.get('category')}: ${cat.get('total', 0):,.2f} ({cat.get('count', 0)})")

    clients = data.get("clients", {})
    if clients:
        rprint(f"\n[bold]Clients:[/bold] {clients.get('active', 0)} active ({clients.get('new', 0)} new, {clients.get('returning', 0)} returning)")

    if data.get("inventory_alerts"):
        rprint(f"\n[yellow]⚠ {data.get('inventory_alerts')} item(s) low on stock[/yellow]")


@app.command("trends")
def trends(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="Compare current vs previous period"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Scope filter (default: global scope, 'all' for cross-scope)"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
):
    """Compare current period to previous."""
    client = get_scoped_client(ctx, scope, default_all=False)
    params = build_period_params(period, from_date, to_date)
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method
    result = client.summary_trends(**params)
    data = result.get("data", result)

    current = data.get("current", {})
    previous = data.get("previous", {})
    change = data.get("change", {})
    trend_val = data.get("trend", "stable")

    trend_emoji = {"up": "📈", "down": "📉", "stable": "➡️"}.get(trend_val, "")

    rprint(f"[bold]Trends ({period}) {trend_emoji}[/bold]")
    rprint()

    inc_change = change.get("income", {})
    inc_pct = inc_change.get("percent", 0)
    inc_color = "green" if inc_pct >= 0 else "red"
    rprint(f"  Income:   ${current.get('income', 0):,.2f} vs ${previous.get('income', 0):,.2f}")
    rprint(f"            [{inc_color}]{inc_pct:+.1f}%[/{inc_color}] (${inc_change.get('amount', 0):+,.2f})")

    exp_change = change.get("expenses", {})
    exp_pct = exp_change.get("percent", 0)
    exp_color = "green" if exp_pct <= 0 else "red"
    rprint(f"  Expenses: ${current.get('expenses', 0):,.2f} vs ${previous.get('expenses', 0):,.2f}")
    rprint(f"            [{exp_color}]{exp_pct:+.1f}%[/{exp_color}] (${exp_change.get('amount', 0):+,.2f})")

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
    scope: Optional[str] = typer.Option(None, "--scope", help="Scope filter (default: global scope, 'all' for cross-scope)"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
):
    """Show income breakdown by day of week."""
    client = get_scoped_client(ctx, scope, default_all=False)
    params = build_period_params(period, from_date, to_date)
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method
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
    scope: Optional[str] = typer.Option(None, "--scope", help="Scope filter ('all' or omit for all scopes)"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
):
    """Show income/expense/profit grouped by scope."""
    client = get_scoped_client(ctx, scope, default_all=True)
    params = build_period_params(period, from_date, to_date)
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method
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


@app.command("by-month")
def by_month(
    ctx: typer.Context,
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD), default: 12 months ago"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD), default: today"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Scope filter ('all' or omit for all scopes)"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """Show monthly P&L breakdown."""
    client = get_scoped_client(ctx, scope, default_all=True)
    params: dict = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method

    result = client.summary_by_month(**params)
    data = result.get("data", result)
    months = data.get("months", [])
    period_info = data.get("period", {})

    if format == "json":
        import json
        print(json.dumps(data, indent=2))
        return

    rprint(f"[bold]Monthly P&L: {period_info.get('from', '')} → {period_info.get('to', '')}[/bold]")
    if source:
        rprint(f"[dim]Source: {source}[/dim]")
    rprint()

    if not months:
        rprint("[yellow]No data for selected period.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Month")
    table.add_column("Income", justify="right")
    table.add_column("Expenses", justify="right")
    table.add_column("Profit", justify="right")
    table.add_column("Txns", justify="right")

    for m in months:
        profit = m.get("profit", 0)
        profit_color = "green" if profit >= 0 else "red"
        total_txns = m.get("income_count", 0) + m.get("expense_count", 0)
        table.add_row(
            m.get("month", ""),
            f"${m.get('income', 0):,.2f}",
            f"${m.get('expenses', 0):,.2f}",
            f"[{profit_color}]${profit:,.2f}[/{profit_color}]",
            str(total_txns),
        )

    rprint(table)


@app.command("by-category")
def by_category(
    ctx: typer.Context,
    period: str = typer.Option("month", "--period", "-p", help="Period to analyze"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (for custom period)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (for custom period)"),
    scope: Optional[str] = typer.Option(None, "--scope", help="Scope filter ('all' or omit for all scopes)"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter: income or expense"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter: bank, cash, agent, or all"),
    payment_method: Optional[str] = typer.Option(None, "--payment-method", help="Filter by payment method"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max categories to show"),
):
    """Show spending/income breakdown by category."""
    client = get_scoped_client(ctx, scope, default_all=True)
    params = build_period_params(period, from_date, to_date)
    if type:
        params["type"] = type
    if source:
        params["source"] = source
    if payment_method:
        params["payment_method"] = payment_method
    params["limit"] = limit

    result = client.summary_by_category(**params)
    data = result.get("data", result)
    categories = data.get("categories", [])
    totals = data.get("totals", {})
    period_info = data.get("period", {})

    rprint(f"[bold]By Category: {period_info.get('from', '')} to {period_info.get('to', '')}[/bold]")
    rprint()

    if not categories:
        rprint("[yellow]No data for selected period.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Category")
    table.add_column("Type")
    table.add_column("Total", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("%", justify="right")

    for cat in categories:
        cat_type = cat.get("type", "")
        type_color = "green" if cat_type == "income" else "red"
        table.add_row(
            cat.get("category", ""),
            f"[{type_color}]{cat_type}[/{type_color}]",
            f"${cat.get('total', 0):,.2f}",
            str(cat.get("count", 0)),
            f"{cat.get('percent', 0):.1f}%",
        )

    rprint(table)
    rprint()
    rprint(f"  [green]Total Income:[/green]   ${totals.get('income', 0):,.2f}")
    rprint(f"  [red]Total Expenses:[/red] ${totals.get('expenses', 0):,.2f}")


@app.command("pulse")
def pulse(
    ctx: typer.Context,
):
    """Household financial overview — always cross-scope."""
    client = KeiClient(scope=None)
    today_str = date.today().isoformat()

    # 1. Net worth from latest household snapshot
    try:
        snap = client.snapshot_latest(scope="household")
        # Response has top-level id/scope/date/data; net worth is in data.net_worth
        snap_inner = snap.get("data", snap)
        nw = snap_inner.get("net_worth", {})
        if isinstance(nw, dict):
            net_worth = nw.get("net", 0)
            assets = nw.get("total_assets", 0)
            liabilities = nw.get("total_liabilities", 0)
        else:
            net_worth = nw
            assets = snap_inner.get("total_assets", 0)
            liabilities = snap_inner.get("total_liabilities", 0)
        has_snapshot = True
    except SystemExit:
        has_snapshot = False
        net_worth = assets = liabilities = 0

    # 2. This month by scope
    try:
        scope_result = client.summary_by_scope(period="month")
        scope_data = scope_result.get("data", scope_result)
        scopes = scope_data.get("scopes", [])
    except SystemExit:
        scopes = []

    # 3. Trends (month vs previous month)
    try:
        trends_result = client.summary_trends(period="month")
        trends_data = trends_result.get("data", trends_result)
    except SystemExit:
        trends_data = {}

    # Render
    rprint(f"[bold]═══ Household Pulse — {today_str} ═══[/bold]")
    rprint()

    if has_snapshot:
        rprint(f"  [bold]Net Worth:[/bold] ${net_worth:,.2f}")
        rprint(f"    Assets:      ${assets:,.2f}")
        rprint(f"    Liabilities: ${liabilities:,.2f}")
    else:
        rprint("  [dim]No snapshot data available[/dim]")

    rprint()
    rprint("[bold]── This Month by Scope ──[/bold]")

    if scopes:
        table = Table(show_header=True, box=None, pad_edge=False)
        table.add_column("Scope", min_width=10)
        table.add_column("Income", justify="right")
        table.add_column("Expense", justify="right")
        table.add_column("Net", justify="right")

        for s in scopes:
            inc = s.get("income", {}).get("total", 0)
            exp = s.get("expenses", {}).get("total", 0)
            net = s.get("profit", 0)
            net_color = "green" if net >= 0 else "red"
            table.add_row(
                s.get("scope", ""),
                f"${inc:,.2f}",
                f"${exp:,.2f}",
                f"[{net_color}]${net:,.2f}[/{net_color}]",
            )
        rprint(table)
    else:
        rprint("  [dim]No scope data this month[/dim]")

    # Trends comparison
    current = trends_data.get("current", {})
    previous = trends_data.get("previous", {})
    change = trends_data.get("change", {})

    if current and previous:
        rprint()
        rprint("[bold]── vs Last Month ──[/bold]")

        cur_inc = current.get("income", 0)
        prev_inc = previous.get("income", 0)
        inc_pct = change.get("income", {}).get("percent", 0)
        inc_color = "green" if inc_pct >= 0 else "red"

        cur_exp = current.get("expenses", 0)
        prev_exp = previous.get("expenses", 0)
        exp_pct = change.get("expenses", {}).get("percent", 0)
        exp_color = "green" if exp_pct <= 0 else "red"

        rprint(f"  Income:   ${prev_inc:,.2f} → ${cur_inc:,.2f}  [{inc_color}]({inc_pct:+.1f}%)[/{inc_color}]")
        rprint(f"  Expenses: ${prev_exp:,.2f} → ${cur_exp:,.2f}  [{exp_color}]({exp_pct:+.1f}%)[/{exp_color}]")
