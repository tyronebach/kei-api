"""Utility functions for kei CLI."""

from typing import Optional
from rich import print as rprint


def resolve_id(items: list, short_id: str, id_field: str = "id") -> Optional[str]:
    """Resolve a truncated ID to full UUID via prefix match.
    
    Args:
        items: List of records with ID field
        short_id: Truncated or full ID to match
        id_field: Name of the ID field (default: "id")
    
    Returns:
        Full UUID if exactly one match, None otherwise
    """
    # If it looks like a full UUID (32 chars), return as-is
    if len(short_id) >= 32:
        return short_id
    
    matches = [
        item[id_field] for item in items 
        if item.get(id_field, "").startswith(short_id)
    ]
    
    if len(matches) == 1:
        return matches[0]
    elif len(matches) == 0:
        rprint(f"[red]No match for ID prefix: {short_id}[/red]")
        return None
    else:
        rprint(f"[red]Ambiguous ID prefix: {short_id} matches {len(matches)} records[/red]")
        for m in matches[:5]:
            rprint(f"  {m[:8]}...")
        return None
