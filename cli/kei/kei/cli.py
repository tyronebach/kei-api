"""Main CLI entry point."""

from typing import Optional

import typer
from rich import print as rprint

from . import __version__
from .config import get_api_base, get_default_scope, load_config, save_config
from .entities import app as entities_app
from .items import app as items_app
from .lists import app as lists_app
from .services import app as services_app
from .summary import app as summary_app
from .transactions import app as transactions_app

app = typer.Typer(
    name="kei",
    help="Agent-first data management CLI.",
    no_args_is_help=True,
)

# Register subcommands
app.add_typer(entities_app, name="entity")
app.add_typer(transactions_app, name="tx")
app.add_typer(items_app, name="item")
app.add_typer(services_app, name="service")
app.add_typer(lists_app, name="list")
app.add_typer(summary_app, name="summary")


@app.callback()
def main(
    ctx: typer.Context,
    scope: Optional[str] = typer.Option(
        None,
        "--scope", "-s",
        help="Scope (salon, home, etc.). Overrides KEI_SCOPE env var.",
        envvar="KEI_SCOPE",
    ),
    version: bool = typer.Option(
        False,
        "--version", "-v",
        help="Show version and exit",
        is_eager=True,
    ),
):
    """Kei CLI - Agent-first data management.

    Global options:

      --scope / -s: Set scope for all commands (e.g., --scope salon)

    Environment variables:

      KEI_API_BASE: API base URL (default: http://localhost:8081)
      KEI_API_TOKEN: API bearer token
      KEI_SCOPE: Default scope

    Configuration file: ~/.config/kei/config.yaml
    """
    if version:
        rprint(f"kei-cli {__version__}")
        raise typer.Exit()

    # Use default scope from config if not provided
    effective_scope = scope or get_default_scope()
    ctx.ensure_object(dict)
    ctx.obj["scope"] = effective_scope


@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Show current config"),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Set API base URL"),
    token: Optional[str] = typer.Option(None, "--token", help="Set API token"),
    default_scope: Optional[str] = typer.Option(None, "--default-scope", help="Set default scope"),
):
    """Configure Kei CLI."""
    config = load_config()

    if show:
        rprint("[bold]Current config:[/bold]")
        rprint(f"  API base: {config.get('api_base', 'http://localhost:8081')}")
        rprint(f"  Token: {'***' if config.get('token') else '(not set)'}")
        rprint(f"  Default scope: {config.get('default_scope', '(not set)')}")
        return

    updated = False
    if api_base:
        config["api_base"] = api_base
        updated = True
    if token:
        config["token"] = token
        updated = True
    if default_scope:
        config["default_scope"] = default_scope
        updated = True

    if updated:
        save_config(config)
        rprint("[green]Config saved to ~/.config/kei/config.yaml[/green]")
    else:
        rprint("Use --show to view config, or set options with --api-base, --token, --default-scope")


@app.command("health")
def health():
    """Check API health."""
    import httpx
    base = get_api_base()
    try:
        r = httpx.get(f"{base}/health", timeout=5.0)
        if r.status_code == 200 and r.json().get("status") == "ok":
            rprint(f"[green]✓ API healthy[/green] ({base})")
        else:
            rprint(f"[yellow]API responded but unhealthy: {r.text}[/yellow]")
    except Exception as e:
        rprint(f"[red]✗ Cannot reach API at {base}[/red]")
        rprint(f"  Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
