"""HTTP client for Kei API."""

import sys
from typing import Any, Optional

import httpx
from rich.console import Console

from .config import get_api_base, get_token
from .utils import resolve_id

console = Console(stderr=True)


class KeiClient:
    """Kei API client."""

    def __init__(self, scope: Optional[str] = None):
        self.base_url = get_api_base()
        self.token = get_token()
        self.scope = scope
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def _handle_response(self, response: httpx.Response) -> Any:
        """Handle API response, exit on error."""
        if response.status_code >= 400:
            details = None
            try:
                error = response.json()
                if isinstance(error, dict):
                    detail = error.get("message") or error.get("detail") or response.text
                    details = error.get("details")
                else:
                    detail = str(error)
            except Exception:
                detail = response.text
            console.print(f"[red]Error ({response.status_code}):[/red] {detail}")
            if details:
                console.print(f"[dim]{details}[/dim]")
            if response.status_code == 401 and not self.token:
                console.print(
                    "[yellow]Tip:[/yellow] set KEI_API_TOKEN or run `kei config --token <token>`."
                )
            sys.exit(1)
        return response.json()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send an HTTP request and normalize transport errors."""
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            console.print(f"[red]Connection error:[/red] {exc}")
            console.print(f"[dim]API base:[/dim] {self.base_url}")
            sys.exit(1)

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return self._request("POST", path, **kwargs)

    def _put(self, path: str, **kwargs) -> httpx.Response:
        return self._request("PUT", path, **kwargs)

    def _delete(self, path: str, **kwargs) -> httpx.Response:
        return self._request("DELETE", path, **kwargs)

    def _add_scope(self, params: dict) -> dict:
        """Add scope to params if set."""
        if self.scope and "scope" not in params:
            params["scope"] = self.scope
        return params

    def _add_scope_body(self, body: dict) -> dict:
        """Add scope to body if set."""
        if self.scope and "scope" not in body:
            body["scope"] = self.scope
        return body

    def _require_scope(self, scope: Any, context: str) -> None:
        """Exit when a write command requires scope but none is set."""
        if isinstance(scope, str) and scope.strip():
            return
        console.print(
            f"[red]{context} requires scope.[/red] Use `--scope`, KEI_SCOPE, or `kei config --default-scope`."
        )
        sys.exit(1)

    def _resolve_prefix(self, short_id: str, list_endpoint: str) -> str:
        """Resolve a short ID prefix to full UUID via listing.

        If the ID is already >= 32 chars (full UUID), returns as-is.
        Fetches records from list_endpoint and prefix-matches.
        On ambiguity or no match, exits with error.
        """
        if len(short_id.replace("-", "")) >= 32:
            return short_id
        params = self._add_scope({"limit": 200})
        try:
            r = self._get(list_endpoint, params=params)
            if r.status_code < 400:
                data = r.json().get("data", [])
                resolved = resolve_id(data, short_id)
                if resolved:
                    return resolved
                # resolve_id already printed error; exit
                sys.exit(1)
        except Exception:
            pass
        return short_id

    # === Entities ===

    def entity_create(self, **data) -> dict:
        """Create an entity."""
        data = self._add_scope_body(data)
        self._require_scope(data.get("scope"), "Creating entities")
        r = self._post("/api/entities", json=data)
        return self._handle_response(r)

    def entity_list(self, **params) -> dict:
        """List/search entities."""
        params = self._add_scope(params)
        r = self._get("/api/entities", params=params)
        return self._handle_response(r)

    def entity_get(self, entity_id: str) -> dict:
        """Get entity by ID."""
        entity_id = self._resolve_prefix(entity_id, "/api/entities")
        r = self._get(f"/api/entities/{entity_id}")
        return self._handle_response(r)

    def entity_update(self, entity_id: str, **data) -> dict:
        """Update an entity."""
        entity_id = self._resolve_prefix(entity_id, "/api/entities")
        r = self._put(f"/api/entities/{entity_id}", json=data)
        return self._handle_response(r)

    def entity_delete(self, entity_id: str) -> dict:
        """Delete an entity."""
        entity_id = self._resolve_prefix(entity_id, "/api/entities")
        r = self._delete(f"/api/entities/{entity_id}")
        return self._handle_response(r)

    def entity_activity(self, entity_id: str) -> dict:
        """Get entity activity/profile."""
        entity_id = self._resolve_prefix(entity_id, "/api/entities")
        r = self._get(f"/api/entities/{entity_id}/activity")
        return self._handle_response(r)

    def entity_insights(self, **params) -> dict:
        """Get entity insights."""
        params = self._add_scope(params)
        r = self._get("/api/entities/insights", params=params)
        return self._handle_response(r)

    # === Transactions ===

    def tx_create(self, **data) -> dict:
        """Create a transaction."""
        data = self._add_scope_body(data)
        self._require_scope(data.get("scope"), "Creating transactions")
        r = self._post("/api/transactions", json=data)
        return self._handle_response(r)

    def tx_list(self, **params) -> dict:
        """List transactions."""
        params = self._add_scope(params)
        r = self._get("/api/transactions", params=params)
        return self._handle_response(r)

    def tx_get(self, tx_id: str) -> dict:
        """Get transaction by ID."""
        tx_id = self._resolve_prefix(tx_id, "/api/transactions")
        r = self._get(f"/api/transactions/{tx_id}")
        return self._handle_response(r)

    def tx_update(self, tx_id: str, **data) -> dict:
        """Update a transaction."""
        tx_id = self._resolve_prefix(tx_id, "/api/transactions")
        r = self._put(f"/api/transactions/{tx_id}", json=data)
        return self._handle_response(r)

    def tx_delete(self, tx_id: str) -> dict:
        """Delete a transaction."""
        tx_id = self._resolve_prefix(tx_id, "/api/transactions")
        r = self._delete(f"/api/transactions/{tx_id}")
        return self._handle_response(r)

    # === Items (Inventory) ===

    def item_create(self, **data) -> dict:
        """Create an item."""
        data = self._add_scope_body(data)
        self._require_scope(data.get("scope"), "Creating items")
        r = self._post("/api/items", json=data)
        return self._handle_response(r)

    def item_list(self, **params) -> dict:
        """List/search items."""
        params = self._add_scope(params)
        r = self._get("/api/items", params=params)
        return self._handle_response(r)

    def item_get(self, item_id: str) -> dict:
        """Get item by ID."""
        item_id = self._resolve_prefix(item_id, "/api/items")
        r = self._get(f"/api/items/{item_id}")
        return self._handle_response(r)

    def item_update(self, item_id: str, **data) -> dict:
        """Update an item."""
        item_id = self._resolve_prefix(item_id, "/api/items")
        r = self._put(f"/api/items/{item_id}", json=data)
        return self._handle_response(r)

    def item_delete(self, item_id: str) -> dict:
        """Delete an item."""
        item_id = self._resolve_prefix(item_id, "/api/items")
        r = self._delete(f"/api/items/{item_id}")
        return self._handle_response(r)

    def item_low_stock(self, **params) -> dict:
        """Get low-stock items."""
        params = self._add_scope(params)
        r = self._get("/api/items/low-stock", params=params)
        return self._handle_response(r)

    def item_adjust(self, item_id: str, **data) -> dict:
        """Adjust item stock."""
        item_id = self._resolve_prefix(item_id, "/api/items")
        r = self._post(f"/api/items/{item_id}/adjust", json=data)
        return self._handle_response(r)

    def item_movements(self, item_id: str) -> dict:
        """Get item movement history."""
        item_id = self._resolve_prefix(item_id, "/api/items")
        r = self._get(f"/api/items/{item_id}/movements")
        return self._handle_response(r)

    # === Lists ===

    def list_names(self, **params) -> dict:
        """Get list names."""
        params = self._add_scope(params)
        r = self._get("/api/lists", params=params)
        return self._handle_response(r)

    def list_items(self, **params) -> dict:
        """Get list items."""
        params = self._add_scope(params)
        r = self._get("/api/lists/items", params=params)
        return self._handle_response(r)

    def list_add_item(self, **data) -> dict:
        """Add item to list."""
        data = self._add_scope_body(data)
        self._require_scope(data.get("scope"), "Adding list items")
        r = self._post("/api/lists/items", json=data)
        return self._handle_response(r)

    def list_update_item(self, item_id: str, **data) -> dict:
        """Update list item."""
        item_id = self._resolve_prefix(item_id, "/api/lists/items")
        r = self._put(f"/api/lists/items/{item_id}", json=data)
        return self._handle_response(r)

    def list_delete_item(self, item_id: str) -> dict:
        """Delete list item."""
        item_id = self._resolve_prefix(item_id, "/api/lists/items")
        r = self._delete(f"/api/lists/items/{item_id}")
        return self._handle_response(r)

    def list_clear(self, **params) -> dict:
        """Clear a list."""
        params = self._add_scope(params)
        self._require_scope(params.get("scope"), "Clearing lists")
        r = self._delete("/api/lists", params=params)
        return self._handle_response(r)

    # === Services ===

    def service_create(self, **data) -> dict:
        """Create a service."""
        data = self._add_scope_body(data)
        self._require_scope(data.get("scope"), "Creating services")
        r = self._post("/api/services", json=data)
        return self._handle_response(r)

    def service_list(self, **params) -> dict:
        """List services."""
        params = self._add_scope(params)
        r = self._get("/api/services", params=params)
        return self._handle_response(r)

    def service_get(self, service_id: str) -> dict:
        """Get service by ID."""
        service_id = self._resolve_prefix(service_id, "/api/services")
        r = self._get(f"/api/services/{service_id}")
        return self._handle_response(r)

    def service_update(self, service_id: str, **data) -> dict:
        """Update a service."""
        service_id = self._resolve_prefix(service_id, "/api/services")
        r = self._put(f"/api/services/{service_id}", json=data)
        return self._handle_response(r)

    def service_delete(self, service_id: str) -> dict:
        """Delete a service."""
        service_id = self._resolve_prefix(service_id, "/api/services")
        r = self._delete(f"/api/services/{service_id}")
        return self._handle_response(r)


    # === Summary ===

    def summary(self, **params) -> dict:
        """Get summary."""
        params = self._add_scope(params)
        r = self._get("/api/summary", params=params)
        return self._handle_response(r)

    def summary_trends(self, **params) -> dict:
        """Get trends."""
        params = self._add_scope(params)
        r = self._get("/api/summary/trends", params=params)
        return self._handle_response(r)

    def summary_by_day(self, **params) -> dict:
        """Get by-day breakdown."""
        params = self._add_scope(params)
        r = self._get("/api/summary/by-day", params=params)
        return self._handle_response(r)

    def summary_by_scope(self, **params) -> dict:
        """Get summary grouped by scope."""
        params = self._add_scope(params)
        r = self._get("/api/summary/by-scope", params=params)
        return self._handle_response(r)
