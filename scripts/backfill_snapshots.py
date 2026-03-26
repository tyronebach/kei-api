#!/usr/bin/env python3
"""Backfill financial snapshots from JSON files into Kei API."""

import json
import os
import sys
from pathlib import Path

import requests

SNAPSHOT_DIR = Path.home() / "clawd-agents/household/financial_snapshots"
API_URL = os.getenv("KEI_API_URL", "http://localhost:8081")
API_TOKEN = os.getenv("KEI_API_TOKEN", "test-token")


def main():
    files = sorted(SNAPSHOT_DIR.glob("2026-*.json"))
    if not files:
        print("No snapshot files found")
        sys.exit(1)

    print(f"Found {len(files)} snapshot files")
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    ok = 0
    for f in files:
        data = json.loads(f.read_text())
        date = data.get("date", f.stem)
        payload = {"scope": "household", "date": date, "data": data}
        resp = requests.post(f"{API_URL}/api/snapshots", json=payload, headers=headers)
        if resp.status_code in (200, 201):
            print(f"  ✓ {date}")
            ok += 1
        else:
            print(f"  ✗ {date}: {resp.status_code} {resp.text}")

    print(f"\nBackfilled {ok}/{len(files)} snapshots")


if __name__ == "__main__":
    main()
