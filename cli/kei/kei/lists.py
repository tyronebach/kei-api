"""List commands (shopping, todo, etc.)."""

from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="list", help="Manage lists (shopping, todo, etc.).")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


@app.command("names")
def names(ctx: typer.Context):
    """Show all list names and counts."""
    client = get_client(ctx)
    result = client.list_names()
    lists = result.get("data", [])

    if not lists:
        rprint("[yellow]No lists found.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("List")
    table.add_column("Total", justify="right")
    table.add_column("Done", justify="right")
    table.add_column("Pending", justify="right")

    for lst in lists:
        table.add_row(
            lst.get("list", ""),
            str(lst.get("total", 0)),
            str(lst.get("checked", 0)),
            str(lst.get("unchecked", 0)),
        )

    rprint(table)


@app.command("show")
def show(
    ctx: typer.Context,
    list_name: str = typer.Argument(..., help="List name (shopping, todo, etc.)"),
    all: bool = typer.Option(False, "--all", "-a", help="Include checked items"),
):
    """Show items in a list."""
    client = get_client(ctx)
    params = {"list": list_name}
    if not all:
        params["checked"] = "false"

    result = client.list_items(**params)
    items = result.get("data", [])

    if not items:
        rprint(f"[yellow]{list_name} is empty.[/yellow]")
        return

    rprint(f"[bold]{list_name}:[/bold]")
    for item in items:
        checked = item.get("checked", False)
        content = item.get("content", "")
        item_id = item.get("id", "")[:8]

        if checked:
            rprint(f"  [dim]✓ {content}[/dim] [dim]({item_id})[/dim]")
        else:
            rprint(f"  • {content} [dim]({item_id})[/dim]")


@app.command("add")
def add(
    ctx: typer.Context,
    list_name: str = typer.Argument(..., help="List name (shopping, todo, etc.)"),
    content: str = typer.Argument(..., help="Item content"),
):
    """Add an item to a list."""
    client = get_client(ctx)
    result = client.list_add_item(list=list_name, content=content)
    item = result.get("data", result)
    rprint(f"[green]Added to {list_name}:[/green] {content}")


@app.command("check")
def check(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID to check off (full or truncated)"),
):
    """Check off an item."""
    client = get_client(ctx)
    item_id = client._resolve_prefix(item_id, "/api/lists/items")
    
    client.list_update_item(item_id, checked=True)
    rprint(f"[green]✓ Checked off {item_id[:8]}[/green]")


@app.command("uncheck")
def uncheck(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID to uncheck (full or truncated)"),
):
    """Uncheck an item."""
    client = get_client(ctx)
    item_id = client._resolve_prefix(item_id, "/api/lists/items")
    
    client.list_update_item(item_id, checked=False)
    rprint(f"[green]Unchecked {item_id[:8]}[/green]")


@app.command("remove")
def remove(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID to remove (full or truncated)"),
):
    """Remove an item from a list."""
    client = get_client(ctx)
    item_id = client._resolve_prefix(item_id, "/api/lists/items")
    
    client.list_delete_item(item_id)
    rprint(f"[green]Removed {item_id[:8]}[/green]")


@app.command("clear")
def clear(
    ctx: typer.Context,
    list_name: str = typer.Argument(..., help="List name to clear"),
    checked_only: bool = typer.Option(False, "--checked-only", "-c", help="Only clear checked items"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Clear all items from a list."""
    if not force:
        msg = f"Clear checked items from {list_name}?" if checked_only else f"Clear ALL items from {list_name}?"
        confirm = typer.confirm(msg)
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    params = {"list": list_name}
    if checked_only:
        params["checked_only"] = "true"

    client.list_clear(**params)
    what = "checked items" if checked_only else "all items"
    rprint(f"[green]Cleared {what} from {list_name}[/green]")


@app.command("update")
def update(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="Item ID (full or truncated)"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="New content"),
    move_to: Optional[str] = typer.Option(None, "--move-to", "-m", help="Move to different list"),
):
    """Update a list item."""
    client = get_client(ctx)
    item_id = client._resolve_prefix(item_id, "/api/lists/items")
    
    data = {}
    if content:
        data["content"] = content
    if move_to:
        data["list"] = move_to

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    client.list_update_item(item_id, **data)
    rprint(f"[green]Updated {item_id[:8]}[/green]")
