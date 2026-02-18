"""Entity commands."""

from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table

from .client import KeiClient
from .utils import resolve_id

app = typer.Typer(name="entity", help="Manage entities (clients, people, businesses).")


def get_client(ctx: typer.Context) -> KeiClient:
    return KeiClient(scope=ctx.obj.get("scope") if ctx.obj else None)


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Entity name"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Entity type (client, vendor, etc.)"),
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="Phone number"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Notes"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
):
    """Add a new entity."""
    client = get_client(ctx)
    data = {"name": name}
    if type:
        data["type"] = type
    if phone:
        data["phone"] = phone
    if email:
        data["email"] = email
    if notes:
        data["notes"] = notes
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    result = client.entity_create(**data)
    entity = result.get("data", result)
    rprint(f"[green]Created entity:[/green] {entity.get('name')} (ID: {entity.get('id')})")


@app.command("list")
def list_entities(
    ctx: typer.Context,
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
):
    """List all entities."""
    client = get_client(ctx)
    params = {"limit": limit}
    if type:
        params["type"] = type
    if tag:
        params["tag"] = tag

    result = client.entity_list(**params)
    entities = result.get("data", [])
    meta = result.get("meta", {})

    if not entities:
        rprint("[yellow]No entities found.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Phone")

    for e in entities:
        table.add_row(
            e.get("id", "")[:8],
            e.get("name", ""),
            e.get("type", "-"),
            e.get("phone", "-"),
        )

    rprint(table)
    rprint(f"[dim]Showing {len(entities)} of {meta.get('total', len(entities))}[/dim]")


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query (name, phone, email)"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
):
    """Search for entities (typo-tolerant)."""
    client = get_client(ctx)
    params = {"search": query, "limit": limit}
    if type:
        params["type"] = type
    if tag:
        params["tag"] = tag

    result = client.entity_list(**params)
    entities = result.get("data", [])
    meta = result.get("meta", {})

    if not entities:
        rprint("[yellow]No entities found.[/yellow]")
        return

    # Show confidence signal
    if meta.get("confident"):
        rprint(f"[green]✓ Confident match:[/green] {meta.get('best_match')}")
    elif len(entities) > 1:
        rprint(f"[yellow]Multiple matches ({len(entities)}) — please disambiguate.[/yellow]")

    table = Table(show_header=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Phone")
    table.add_column("Score", justify="right")

    for e in entities:
        table.add_row(
            e.get("id", "")[:8],
            e.get("name", ""),
            e.get("type", "-"),
            e.get("phone", "-"),
            f"{e.get('score', 0):.2f}" if "score" in e else "-",
        )

    rprint(table)


@app.command("get")
def get(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID (full or truncated)"),
):
    """Get entity details."""
    client = get_client(ctx)
    
    # Resolve truncated ID
    if len(entity_id) < 32:
        all_entities = client.entity_list(limit=200).get("data", [])
        entity_id = resolve_id(all_entities, entity_id)
        if not entity_id:
            raise typer.Exit(1)
    
    result = client.entity_get(entity_id)
    entity = result.get("data", result)

    rprint(f"[bold]{entity.get('name')}[/bold]")
    rprint(f"  ID: {entity.get('id')}")
    rprint(f"  Type: {entity.get('type', '-')}")
    rprint(f"  Phone: {entity.get('phone', '-')}")
    rprint(f"  Email: {entity.get('email', '-')}")
    if entity.get("notes"):
        rprint(f"  Notes: {entity.get('notes')}")
    if entity.get("tags"):
        rprint(f"  Tags: {', '.join(entity.get('tags', []))}")


@app.command("activity")
def activity(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID (full or truncated)"),
):
    """Get entity activity/profile (visit history, spend, etc.)."""
    client = get_client(ctx)
    
    # Resolve truncated ID
    if len(entity_id) < 32:
        all_entities = client.entity_list(limit=200).get("data", [])
        entity_id = resolve_id(all_entities, entity_id)
        if not entity_id:
            raise typer.Exit(1)
    
    result = client.entity_activity(entity_id)
    data = result.get("data", result)

    rprint(f"[bold]{data.get('name')}[/bold]")
    rprint(f"  Total spend: ${data.get('total_spend', 0):.2f}")
    rprint(f"  Visits: {data.get('visit_count', 0)}")
    rprint(f"  Avg spend: ${data.get('avg_spend', 0):.2f}")
    if data.get("first_visit"):
        rprint(f"  First visit: {data.get('first_visit')}")
    if data.get("last_visit"):
        rprint(f"  Last visit: {data.get('last_visit')}")
    if data.get("notes"):
        rprint(f"  Notes: {data.get('notes')}")

    if data.get("by_category"):
        rprint("\n[bold]By Category:[/bold]")
        for cat in data["by_category"]:
            rprint(f"  {cat.get('category')}: ${cat.get('total', 0):.2f} ({cat.get('count', 0)} visits)")


@app.command("update")
def update(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID (full or truncated)"),
    name: Optional[str] = typer.Option(None, "--name", help="New name"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="New type"),
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="New phone"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="New email"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="New notes"),
    tags: Optional[str] = typer.Option(None, "--tags", help="New tags (comma-separated)"),
):
    """Update an entity."""
    client = get_client(ctx)
    
    # Resolve truncated ID
    if len(entity_id) < 32:
        all_entities = client.entity_list(limit=200).get("data", [])
        entity_id = resolve_id(all_entities, entity_id)
        if not entity_id:
            raise typer.Exit(1)
    
    data = {}
    if name:
        data["name"] = name
    if type:
        data["type"] = type
    if phone:
        data["phone"] = phone
    if email:
        data["email"] = email
    if notes:
        data["notes"] = notes
    if tags:
        data["tags"] = [t.strip() for t in tags.split(",")]

    if not data:
        rprint("[red]No fields to update.[/red]")
        raise typer.Exit(1)

    result = client.entity_update(entity_id, **data)
    rprint(f"[green]Updated entity {entity_id}[/green]")


@app.command("delete")
def delete(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID (full or truncated)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete an entity."""
    client = get_client(ctx)
    
    # Resolve truncated ID
    if len(entity_id) < 32:
        all_entities = client.entity_list(limit=200).get("data", [])
        entity_id = resolve_id(all_entities, entity_id)
        if not entity_id:
            raise typer.Exit(1)
    
    if not force:
        confirm = typer.confirm(f"Delete entity {entity_id[:8]}?")
        if not confirm:
            raise typer.Abort()

    client.entity_delete(entity_id)
    rprint(f"[green]Deleted entity {entity_id[:8]}[/green]")


@app.command("insights")
def insights(
    ctx: typer.Context,
    inactive_days: Optional[int] = typer.Option(None, "--inactive-days", help="Filter by days since last visit"),
    min_visits: Optional[int] = typer.Option(None, "--min-visits", help="Minimum visit count"),
    created_after: Optional[str] = typer.Option(None, "--created-after", help="Created after date (YYYY-MM-DD)"),
    created_before: Optional[str] = typer.Option(None, "--created-before", help="Created before date (YYYY-MM-DD)"),
    sort: str = typer.Option("last_visit", "--sort", "-s", help="Sort by: last_visit, total_spend, visits, name"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
):
    """Get entity insights (inactive clients, top spenders, etc.)."""
    client = get_client(ctx)
    params = {"sort": sort, "limit": limit}
    if inactive_days:
        params["inactive_days"] = inactive_days
    if min_visits:
        params["min_visits"] = min_visits
    if created_after:
        params["created_after"] = created_after
    if created_before:
        params["created_before"] = created_before

    result = client.entity_insights(**params)
    entities = result.get("data", [])

    if not entities:
        rprint("[yellow]No entities found matching criteria.[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Name")
    table.add_column("Last Visit")
    table.add_column("Visits", justify="right")
    table.add_column("Total Spend", justify="right")

    for e in entities:
        table.add_row(
            e.get("name", ""),
            e.get("last_visit", "-"),
            str(e.get("visit_count", 0)),
            f"${e.get('total_spend', 0):.2f}",
        )

    rprint(table)
