"""Snapshot commands."""

import json
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="snapshot", help="Financial snapshots (net worth, accounts, investments).")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


def _fmt_dollar(v) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _render_error(message: str) -> None:
    rprint(f"[red]{message}[/red]")
    raise typer.Exit(1)


def _snapshot_payload(snapshot) -> tuple[str, dict]:
    if not isinstance(snapshot, dict):
        _render_error("Snapshot response must be an object.")

    snap_data = snapshot.get("data", snapshot)
    if not isinstance(snap_data, dict):
        _render_error("Snapshot data must be an object.")

    return snapshot.get("date", ""), snap_data


def _net_worth(snapshot_data: dict) -> dict:
    net_worth = snapshot_data.get("net_worth")
    if not isinstance(net_worth, dict):
        _render_error("Snapshot data is missing required net_worth object.")
    return net_worth


def _render_snapshot(data: dict, verbose: bool = False) -> None:
    """Pretty-print a snapshot."""
    snap_date, snap_data = _snapshot_payload(data)
    nw = _net_worth(snap_data)
    rprint(f"[bold]Financial Snapshot — {snap_date}[/bold]")
    rprint()
    rprint(f"  [bold green]Total Assets:[/bold green]      {_fmt_dollar(nw.get('total_assets'))}")
    rprint(f"  [bold red]Total Liabilities:[/bold red]  {_fmt_dollar(nw.get('total_liabilities'))}")
    rprint(f"  [bold]Net Worth:[/bold]           {_fmt_dollar(nw.get('net'))}")

    # Liquid accounts
    liquid = snap_data.get("liquid_accounts", [])
    if liquid:
        rprint(f"\n[bold]Liquid Accounts[/bold]")
        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Account")
        table.add_column("Owner")
        table.add_column("Balance", justify="right")
        for a in liquid:
            table.add_row(a.get("label", ""), a.get("owner", ""), _fmt_dollar(a.get("balance")))
        rprint(table)

    # Credit cards
    cards = snap_data.get("credit_cards", [])
    if cards:
        rprint(f"\n[bold]Credit Cards[/bold]")
        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Card")
        table.add_column("Owner")
        table.add_column("Owed", justify="right")
        table.add_column("")
        for c in cards:
            flag = "[dim](derived)[/dim]" if c.get("derived") else ""
            table.add_row(c.get("label", ""), c.get("owner", ""), _fmt_dollar(c.get("amount_owed")), flag)
        rprint(table)

    # Investments
    inv = snap_data.get("investments", [])
    if inv:
        rprint(f"\n[bold]Investments[/bold]")
        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Account")
        table.add_column("Value (CAD)", justify="right")
        total_inv = 0.0
        for i in inv:
            val = i.get("value_cad", 0) or 0
            total_inv += val
            table.add_row(i.get("account", ""), _fmt_dollar(val))
        table.add_row("[bold]Total[/bold]", f"[bold]{_fmt_dollar(total_inv)}[/bold]")
        rprint(table)

    # Lines of credit
    loc = snap_data.get("lines_of_credit", [])
    if loc:
        rprint(f"\n[bold]Lines of Credit[/bold]")
        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Account")
        table.add_column("Owner")
        table.add_column("Owed", justify="right")
        for l in loc:
            table.add_row(l.get("label", ""), l.get("owner", ""), _fmt_dollar(l.get("amount_owed")))
        rprint(table)

    # Mortgage
    mortgage = snap_data.get("mortgage_detail", [])
    if mortgage:
        rprint(f"\n[bold]Mortgage[/bold]")
        for m in mortgage:
            rprint(f"  {m.get('label', '')}")
            rprint(f"    Rate: {m.get('interest_rate', '?')}% ({m.get('interest_rate_type', '')})")
            rprint(f"    Next payment: {_fmt_dollar(m.get('next_payment_amount'))} on {m.get('maturity_date', '?')}")

    # Spending
    spending = snap_data.get("spending", [])
    if spending:
        rprint(f"\n[bold]Spending by Scope[/bold]")
        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Scope")
        table.add_column("Month")
        table.add_column("Income", justify="right")
        table.add_column("Expense", justify="right")
        table.add_column("Net", justify="right")
        table.add_column("Txns", justify="right")
        for s in spending:
            net = s.get("net", 0) or 0
            net_color = "green" if net >= 0 else "red"
            table.add_row(
                s.get("scope", ""),
                s.get("month", ""),
                _fmt_dollar(s.get("income")),
                _fmt_dollar(s.get("expense")),
                f"[{net_color}]{_fmt_dollar(net)}[/{net_color}]",
                str(s.get("txns", 0)),
            )
        rprint(table)

    if verbose:
        rprint(f"\n[dim]Full JSON:[/dim]")
        rprint(json.dumps(snap_data, indent=2))


@app.callback(invoke_without_command=True)
def latest(
    ctx: typer.Context,
    scope: str = typer.Option("household", "--scope", "-s", help="Snapshot scope"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include full JSON dump"),
    format: str = typer.Option("rich", "--format", "-f", help="Output format: rich or json"),
):
    """Show latest financial snapshot (default command)."""
    if ctx.invoked_subcommand is not None:
        return

    client = get_client(ctx)
    result = client.snapshot_latest(scope=scope)

    if format == "json":
        print(json.dumps(result, indent=2))
        return

    _render_snapshot(result, verbose=verbose)


@app.command("list")
def list_snapshots(
    ctx: typer.Context,
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Filter by scope"),
    from_date: Optional[str] = typer.Option(None, "--from", help="From date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="To date (YYYY-MM-DD)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List available snapshots."""
    client = get_client(ctx)
    params: dict = {"limit": limit}
    if scope:
        params["scope"] = scope
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    results = client.snapshot_list(**params)

    if format == "json":
        print(json.dumps(results, indent=2))
        return

    if not results:
        rprint("[yellow]No snapshots found.[/yellow]")
        return

    table = Table(show_header=True, padding=(0, 1))
    table.add_column("Date")
    table.add_column("Scope")
    table.add_column("Net Worth", justify="right")
    table.add_column("ID", max_width=12)

    for snap in results:
        _, snap_data = _snapshot_payload(snap)
        nw = _net_worth(snap_data)
        table.add_row(
            snap.get("date", ""),
            snap.get("scope", ""),
            _fmt_dollar(nw.get("net")),
            snap.get("id", "")[:12] + "…",
        )

    rprint(table)
    rprint(f"[dim]{len(results)} snapshot(s)[/dim]")


@app.command("show")
def show_snapshot(
    ctx: typer.Context,
    date: Optional[str] = typer.Argument(None, help="Date (YYYY-MM-DD) or snapshot ID"),
    scope: str = typer.Option("household", "--scope", "-s", help="Scope (used with date lookup)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include full JSON dump"),
    format: str = typer.Option("rich", "--format", "-f", help="Output format: rich or json"),
):
    """Show a specific snapshot by date or ID."""
    client = get_client(ctx)

    if date is None:
        # No argument = latest
        result = client.snapshot_latest(scope=scope)
    elif len(date) > 10:
        # Looks like an ID
        result = client.snapshot_get(date)
    else:
        # Date lookup: list with exact date filter
        results = client.snapshot_list(scope=scope, **{"from": date, "to": date, "limit": 1})
        if not results:
            rprint(f"[red]No snapshot found for {date} (scope={scope})[/red]")
            raise typer.Exit(1)
        result = results[0]

    if format == "json":
        print(json.dumps(result, indent=2))
        return

    _render_snapshot(result, verbose=verbose)


@app.command("diff")
def diff_snapshots(
    ctx: typer.Context,
    date1: str = typer.Argument(..., help="First date (YYYY-MM-DD) — older"),
    date2: Optional[str] = typer.Argument(None, help="Second date (YYYY-MM-DD) — newer. Default: latest"),
    scope: str = typer.Option("household", "--scope", "-s", help="Scope"),
):
    """Compare two snapshots (net worth delta)."""
    client = get_client(ctx)

    # Fetch first snapshot
    results1 = client.snapshot_list(scope=scope, **{"from": date1, "to": date1, "limit": 1})
    if not results1:
        rprint(f"[red]No snapshot for {date1}[/red]")
        raise typer.Exit(1)
    snap1 = results1[0]

    # Fetch second snapshot
    if date2:
        results2 = client.snapshot_list(scope=scope, **{"from": date2, "to": date2, "limit": 1})
        if not results2:
            rprint(f"[red]No snapshot for {date2}[/red]")
            raise typer.Exit(1)
        snap2 = results2[0]
    else:
        snap2 = client.snapshot_latest(scope=scope)

    _, snap_data1 = _snapshot_payload(snap1)
    _, snap_data2 = _snapshot_payload(snap2)
    d1 = _net_worth(snap_data1)
    d2 = _net_worth(snap_data2)

    rprint(f"[bold]Snapshot Diff: {snap1.get('date')} → {snap2.get('date')}[/bold]")
    rprint()

    for key, label in [("total_assets", "Assets"), ("total_liabilities", "Liabilities"), ("net", "Net Worth")]:
        v1 = d1.get(key, 0) or 0
        v2 = d2.get(key, 0) or 0
        delta = v2 - v1
        color = "green" if delta >= 0 else "red"
        if key == "total_liabilities":
            color = "green" if delta <= 0 else "red"
        rprint(f"  {label:20s} {_fmt_dollar(v1):>14s} → {_fmt_dollar(v2):>14s}  [{color}]{delta:+,.2f}[/{color}]")
