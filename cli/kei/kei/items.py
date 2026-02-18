"""Item/inventory commands."""

from datetime import datetime
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="item", help="Manage inventory items.")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Item name"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Category"),
    quantity: int = typer.Option(0, "--qty", "-q", help="Initial quantity"),
    unit: str = typer.Option("unit", "--unit", "-u", help="Unit (bottle, box, etc.)"),
    reorder: Optional[int] = typer.Option(None, "--reorder", "-r", help="Reorder threshold"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
):
    """Add an inventory item."""
    client = get_client(ctx)
    data = {"name": name, "quantity": quantity, "unit": unit}
    if category:
        data["category"] = category
    if reorder is not None:
        data["reorder_threshold"] = reorder
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    result = client.item_create(**data)
    item = result.get("data", result)
    rprint(f"[green]Created item:[/green] {item.get('name')} (ID: {item.get('id', '')[:8]})")


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
):
    """Search for items (typo-tolerant)."""
    client = get_client(ctx)
    params = {"search": query, "limit": limit}
    if category:
        params["category"] = category

    result = client.item_list(**params)
    items = result.get("data", [])
    meta = result.get("meta", {})

    if not items:
        rprint("[yellow]No items found.[/yellow]")
        return

    if meta.get("confident"):
        rprint(f"[green]✓ Confident match:[/green] {meta.get('best_match')}")

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Qty", justify="right")
    table.add_column("Unit")
    table.add_column("Score", justify="right")

    for item in items:
        qty = item.get("quantity", 0)
        reorder = item.get("reorder_threshold")
        qty_str = str(qty)
        if reorder and qty <= reorder:
            qty_str = f"[red]{qty}[/red]"

        table.add_row(
            item.get("id", "")[:8],
            item.get("name", ""),
            item.get("category", "-"),
            qty_str,
            item.get("unit", "unit"),
            f"{item.get('score', 0):.2f}" if "score" in item else "-",
        )

    rprint(table)


@app.command("list")
def list_items(
    ctx: typer.Context,
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
):
    """List all items."""
    client = get_client(ctx)
    params = {"limit": limit}
    if category:
        params["category"] = category

    result = client.item_list(**params)
    items = result.get("data", [])

    if not items:
        rprint("[yellow]No items found.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Qty", justify="right")
    table.add_column("Reorder", justify="right")

    for item in items:
        qty = item.get("quantity", 0)
        reorder = item.get("reorder_threshold")
        qty_str = str(qty)
        if reorder and qty <= reorder:
            qty_str = f"[red]{qty}[/red]"

        table.add_row(
            item.get("id", "")[:8],
            item.get("name", ""),
            item.get("category", "-"),
            qty_str,
            str(reorder) if reorder else "-",
        )

    rprint(table)


@app.command("low-stock")
def low_stock(ctx: typer.Context):
    """Show items below reorder threshold."""
    client = get_client(ctx)
    result = client.item_low_stock()
    items = result.get("data", [])

    if not items:
        rprint("[green]✓ All items are stocked.[/green]")
        return

    rprint(f"[yellow]{len(items)} item(s) low on stock:[/yellow]")
    for item in items:
        rprint(f"  • {item.get('name')}: {item.get('quantity')} {item.get('unit', 'unit')}(s) (reorder at {item.get('reorder_threshold')})")


@app.command("get")
def get(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID"),
):
    """Get item details."""
    client = get_client(ctx)
    result = client.item_get(item_id)
    item = result.get("data", result)

    rprint(f"[bold]{item.get('name')}[/bold]")
    rprint(f"  ID: {item.get('id')}")
    rprint(f"  Category: {item.get('category', '-')}")
    rprint(f"  Quantity: {item.get('quantity', 0)} {item.get('unit', 'unit')}(s)")
    if item.get("reorder_threshold"):
        rprint(f"  Reorder at: {item.get('reorder_threshold')}")
    if item.get("tags"):
        rprint(f"  Tags: {', '.join(item.get('tags', []))}")


@app.command("adjust")
def adjust(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID"),
    in_qty: Optional[int] = typer.Option(None, "--in", help="Add stock (restock)"),
    out_qty: Optional[int] = typer.Option(None, "--out", help="Remove stock (used)"),
    set_qty: Optional[int] = typer.Option(None, "--set", help="Set stock to exact value (inventory count)"),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="Reason for adjustment"),
):
    """Adjust item stock."""
    client = get_client(ctx)

    if sum(x is not None for x in [in_qty, out_qty, set_qty]) != 1:
        rprint("[red]Specify exactly one of --in, --out, or --set[/red]")
        raise typer.Exit(1)

    data = {}
    if in_qty is not None:
        data["type"] = "in"
        data["quantity"] = in_qty
    elif out_qty is not None:
        data["type"] = "out"
        data["quantity"] = out_qty
    else:
        data["type"] = "adjustment"
        data["quantity"] = set_qty

    if reason:
        data["reason"] = reason

    result = client.item_adjust(item_id, **data)
    item = result.get("data", result)
    rprint(f"[green]Adjusted stock.[/green] New quantity: {item.get('quantity', '?')} {item.get('unit', 'unit')}(s)")


@app.command("movements")
def movements(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID"),
):
    """Show stock movement history for an item."""
    client = get_client(ctx)
    result = client.item_movements(item_id)
    movements = result.get("data", [])

    if not movements:
        rprint("[yellow]No movements recorded.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Qty", justify="right")
    table.add_column("Reason")

    for m in movements:
        qty = m.get("quantity", 0)
        type_str = m.get("type", "")
        created_at = m.get("created_at")
        if isinstance(created_at, (int, float)):
            date_str = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
        else:
            date_str = str(created_at or "")[:10]
        if type_str == "in":
            qty_str = f"[green]+{qty}[/green]"
        elif type_str == "out":
            qty_str = f"[red]-{qty}[/red]"
        else:
            qty_str = f"={qty}"

        table.add_row(
            date_str,
            type_str,
            qty_str,
            m.get("reason", "-"),
        )

    rprint(table)


@app.command("update")
def update(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID"),
    name: Optional[str] = typer.Option(None, "--name", help="New name"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="New category"),
    unit: Optional[str] = typer.Option(None, "--unit", "-u", help="New unit"),
    reorder: Optional[int] = typer.Option(None, "--reorder", "-r", help="New reorder threshold"),
):
    """Update an item."""
    client = get_client(ctx)
    data = {}
    if name:
        data["name"] = name
    if category:
        data["category"] = category
    if unit:
        data["unit"] = unit
    if reorder is not None:
        data["reorder_threshold"] = reorder

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    client.item_update(item_id, **data)
    rprint(f"[green]Updated item {item_id[:8]}[/green]")


@app.command("delete")
def delete(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete an item."""
    if not force:
        confirm = typer.confirm(f"Delete item {item_id}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    client.item_delete(item_id)
    rprint(f"[green]Deleted item {item_id[:8]}[/green]")
