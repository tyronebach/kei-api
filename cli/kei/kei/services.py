"""Service commands."""

from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient

app = typer.Typer(name="service", help="Manage service catalog.")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Service name"),
    price: float = typer.Argument(..., help="Price"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Category"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Duration in minutes"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
):
    """Add a service to the catalog."""
    client = get_client(ctx)
    data = {"name": name, "price": price}
    if category:
        data["category"] = category
    if duration:
        data["duration_minutes"] = duration
    if notes:
        data["notes"] = notes
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    result = client.service_create(**data)
    service = result.get("data", result)
    rprint(f"[green]Created service:[/green] {service.get('name')} @ ${service.get('price', 0):.2f} (ID: {service.get('id', '')[:8]})")


@app.command("list")
def list_services(
    ctx: typer.Context,
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
):
    """List all services."""
    client = get_client(ctx)
    params = {"limit": limit}
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag

    result = client.service_list(**params)
    services = result.get("data", [])

    if not services:
        rprint("[yellow]No services found.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Price", justify="right")
    table.add_column("Duration", justify="right")

    for svc in services:
        duration = svc.get("duration_minutes")
        duration_str = f"{duration}m" if duration else "-"

        table.add_row(
            svc.get("id", "")[:8],
            svc.get("name", ""),
            svc.get("category", "-"),
            f"${svc.get('price', 0):.2f}",
            duration_str,
        )

    rprint(table)


@app.command("get")
def get(
    ctx: typer.Context,
    service_id: str = typer.Argument(..., help="Service ID"),
):
    """Get service details."""
    client = get_client(ctx)
    result = client.service_get(service_id)
    svc = result.get("data", result)

    rprint(f"[bold]{svc.get('name')}[/bold]")
    rprint(f"  ID: {svc.get('id')}")
    rprint(f"  Price: ${svc.get('price', 0):.2f}")
    rprint(f"  Category: {svc.get('category', '-')}")
    if svc.get("duration_minutes"):
        rprint(f"  Duration: {svc.get('duration_minutes')} minutes")
    if svc.get("notes"):
        rprint(f"  Notes: {svc.get('notes')}")
    if svc.get("tags"):
        rprint(f"  Tags: {', '.join(svc.get('tags', []))}")


@app.command("update")
def update(
    ctx: typer.Context,
    service_id: str = typer.Argument(..., help="Service ID"),
    name: Optional[str] = typer.Option(None, "--name", help="New name"),
    price: Optional[float] = typer.Option(None, "--price", "-p", help="New price"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="New category"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="New duration in minutes"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="New notes"),
):
    """Update a service."""
    client = get_client(ctx)
    data = {}
    if name:
        data["name"] = name
    if price is not None:
        data["price"] = price
    if category:
        data["category"] = category
    if duration is not None:
        data["duration_minutes"] = duration
    if notes:
        data["notes"] = notes

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    result = client.service_update(service_id, **data)
    svc = result.get("data", result)
    rprint(f"[green]Updated service {service_id[:8]}[/green] - {svc.get('name')} @ ${svc.get('price', 0):.2f}")


@app.command("delete")
def delete(
    ctx: typer.Context,
    service_id: str = typer.Argument(..., help="Service ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a service."""
    if not force:
        confirm = typer.confirm(f"Delete service {service_id}?")
        if not confirm:
            raise typer.Abort()

    client = get_client(ctx)
    client.service_delete(service_id)
    rprint(f"[green]Deleted service {service_id[:8]}[/green]")
