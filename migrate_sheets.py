#!/usr/bin/env python3
"""Migrate data from Google Sheets to kei-api."""

import subprocess
import json
import re
import httpx

API_URL = "http://localhost:8081"
API_TOKEN = "test-token"

def api(method: str, path: str, data: dict | None = None) -> dict:
    """Make API request."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    url = f"{API_URL}{path}"
    
    if method == "GET":
        r = httpx.get(url, headers=headers, timeout=30)
    elif method == "POST":
        r = httpx.post(url, headers=headers, json=data, timeout=30)
    else:
        raise ValueError(f"Unknown method: {method}")
    
    r.raise_for_status()
    return r.json()

def get_sheet(sheet_id: str, range_: str) -> list[dict]:
    """Fetch sheet data using gog CLI and parse to dicts."""
    cmd = [
        "gog", "sheets", "get",
        "--account", "etjiong@gmail.com",
        sheet_id, range_,
        "--json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"Error fetching sheet: {result.stderr}")
        return []
    
    try:
        data = json.loads(result.stdout)
        values = data.get("values", [])
        if not values:
            return []
        
        # First row is headers
        headers = values[0]
        rows = []
        for row_vals in values[1:]:
            # Pad row to match header length
            padded = row_vals + [""] * (len(headers) - len(row_vals))
            row_dict = dict(zip(headers, padded))
            rows.append(row_dict)
        
        return rows
    except json.JSONDecodeError:
        print(f"Failed to parse JSON: {result.stdout[:200]}")
        return []

def parse_amount(val: str) -> float:
    """Parse amount string like '$120.00' or '-$80' to float."""
    if not val:
        return 0.0
    clean = re.sub(r'[^\d.\-]', '', str(val))
    try:
        return float(clean)
    except ValueError:
        return 0.0

def migrate_salon_clients():
    """Migrate salon clients to entities."""
    print("\n=== Migrating Salon Clients ===")
    
    rows = get_sheet("1bO34bt_DHNNlSscDlPMj-z03bwDhMO1G-cZJ4zveXkg", "Clients!A:M")
    if not rows:
        print("No client data found")
        return {}
    
    # Map old IDs to new IDs
    id_map = {}
    
    for row in rows[1:]:  # Skip header
        if len(row) < 2 or not row.get("Name"):
            continue
        
        old_id = row.get("ID", "")
        name = row.get("Name", "").strip()
        if not name:
            continue
        
        entity = {
            "scope": "salon",
            "name": name,
            "type": "client",
            "phone": row.get("Phone", ""),
            "email": row.get("Email", ""),
            "notes": row.get("Notes", ""),
            "tags": [row.get("Status", "active")],
            "meta": {
                "usual_service": row.get("Usual Service", ""),
                "last_visit": row.get("Last Visit", ""),
                "lifetime_spend": row.get("Lifetime Spend", ""),
                "hair_type": row.get("Hair Type", ""),
                "natural_color": row.get("Natural Color", ""),
                "current_color": row.get("Current Color", ""),
                "formulas": row.get("Formulas", ""),
                "old_id": old_id,
            }
        }
        
        try:
            result = api("POST", "/api/entities", entity)
            new_id = result.get("data", {}).get("id", "")
            id_map[name.lower()] = new_id
            print(f"  Created: {name} -> {new_id}")
        except Exception as e:
            print(f"  Failed: {name} - {e}")
    
    return id_map

def migrate_salon_transactions(entity_map: dict):
    """Migrate salon income transactions."""
    print("\n=== Migrating Salon Transactions (Income) ===")
    
    rows = get_sheet("1bO34bt_DHNNlSscDlPMj-z03bwDhMO1G-cZJ4zveXkg", "Transactions!A:H")
    if not rows:
        print("No transaction data found")
        return
    
    count = 0
    for row in rows[1:]:  # Skip header
        date = row.get("Date", "")
        client = row.get("Client", "")
        service = row.get("Service", "")
        amount = parse_amount(row.get("Service Amount", "0"))
        tip = parse_amount(row.get("Tip", "0"))
        paid_via = row.get("Paid Via", "cash")
        notes = row.get("Notes", "")
        is_refund = str(row.get("Is Refund", "")).upper() == "TRUE"
        
        if not date:
            continue
        
        # Lookup entity
        entity_id = entity_map.get(client.lower().strip(), None)
        
        # Determine type
        tx_type = "income"
        if is_refund or amount < 0:
            tx_type = "expense"  # Refunds are negative income / expenses
            amount = abs(amount)
        
        transaction = {
            "scope": "salon",
            "type": tx_type,
            "amount": amount,
            "category": service if service else "service",
            "date": date,
            "description": f"{client} - {service}" if client else service,
            "entity_id": entity_id,
            "payment_method": paid_via.lower() if paid_via else "cash",
            "tags": ["refund"] if is_refund else [],
            "meta": {
                "tip": tip,
                "notes": notes,
            }
        }
        
        try:
            api("POST", "/api/transactions", transaction)
            count += 1
        except Exception as e:
            print(f"  Failed: {date} {client} - {e}")
    
    print(f"  Created {count} income transactions")

def migrate_salon_expenses():
    """Migrate salon expense transactions."""
    print("\n=== Migrating Salon Expenses ===")
    
    rows = get_sheet("1bO34bt_DHNNlSscDlPMj-z03bwDhMO1G-cZJ4zveXkg", "Expenses!A:I")
    if not rows:
        print("No expense data found")
        return
    
    count = 0
    for row in rows[1:]:  # Skip header
        date = row.get("Date", "")
        vendor = row.get("Vendor", "")
        what = row.get("What it was", "")
        category = row.get("Category", "supplies")
        total = parse_amount(row.get("Total", "0"))
        payment = row.get("Payment method", "")
        notes = row.get("Notes", "")
        
        if not date or total == 0:
            continue
        
        transaction = {
            "scope": "salon",
            "type": "expense",
            "amount": total,
            "category": category.lower() if category else "supplies",
            "date": date,
            "description": f"{vendor} - {what}" if what else vendor,
            "payment_method": payment.lower() if payment else None,
            "tags": [],
            "meta": {
                "vendor": vendor,
                "notes": notes,
            }
        }
        
        try:
            api("POST", "/api/transactions", transaction)
            count += 1
        except Exception as e:
            print(f"  Failed: {date} {vendor} - {e}")
    
    print(f"  Created {count} expense transactions")

def migrate_home_transactions():
    """Migrate home budget transactions."""
    print("\n=== Migrating Home Transactions ===")
    
    rows = get_sheet("1LUz5LXr_lQ8bIfA-EXnk1AZ0qIG-yMG_J2N4qBrLR-k", "Clients!A:E")
    if not rows:
        print("No home transaction data found")
        return
    
    count = 0
    for row in rows[1:]:  # Skip header
        date = row.get("Date", "")
        category = row.get("Category", "other")
        description = row.get("Vendor/Description", "")
        amount = parse_amount(row.get("Amount", "0"))
        notes = row.get("Notes", "")
        
        if not date or amount == 0:
            continue
        
        transaction = {
            "scope": "home",
            "type": "expense",
            "amount": amount,
            "category": category.lower() if category else "other",
            "date": date,
            "description": description,
            "tags": [],
            "meta": {
                "notes": notes,
            }
        }
        
        try:
            api("POST", "/api/transactions", transaction)
            count += 1
        except Exception as e:
            print(f"  Failed: {date} {description} - {e}")
    
    print(f"  Created {count} home transactions")

def main():
    print("Starting migration from Google Sheets to kei-api...")
    
    # Check API is up
    try:
        health = api("GET", "/health")
        print(f"API status: {health}")
    except Exception as e:
        print(f"API not available: {e}")
        return
    
    # Migrate in order
    entity_map = migrate_salon_clients()
    migrate_salon_transactions(entity_map)
    migrate_salon_expenses()
    migrate_home_transactions()
    
    print("\n=== Migration Complete ===")

if __name__ == "__main__":
    main()
