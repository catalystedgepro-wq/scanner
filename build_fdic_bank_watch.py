#!/usr/bin/env python3
"""build_fdic_bank_watch.py — FDIC failed banks + Call Report stress metrics.

FDIC Failed Bank List flags institutions resolved. Deposit flights at
mid-banks (SIVB/SBNY/FRC precedent 2026) ripple to REITs (CPT, ESS,
office REITs), regional banks (KRE), big banks (JPM, BAC, C, WFC deposit
beneficiaries).

Sources:
  - FDIC Failed Bank List: banks.data.fdic.gov/api/failures
  - Call Reports via fdic.gov Call Report Data API (no key)

Output: fdic_bank_watch.csv
Columns: failure_date, name, city, state, assets_m, deposits_m,
         acquirer, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fdic_bank_watch.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# FDIC failures API: returns JSON array
URL = (
    "https://banks.data.fdic.gov/api/failures"
    "?filters=FAILYR:%5B2023+TO+2026%5D&sort_by=FAILDATE"
    "&sort_order=DESC&limit=100&format=json"
)


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"fdic: {e}")
        return None


def main() -> None:
    data = fetch() or {}
    recs = (data.get("data") or []) if isinstance(data, dict) else []
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for rec in recs:
        d = rec.get("data", {}) if isinstance(rec, dict) else rec
        rows.append({
            "failure_date": (d.get("FAILDATE") or "")[:10],
            "name": (d.get("NAME") or "")[:100],
            "city": (d.get("CITYST") or d.get("CITY") or "")[:60],
            "state": d.get("STATE") or "",
            "assets_m": d.get("QBFASSET") or d.get("RESTYPE1") or "",
            "deposits_m": d.get("QBFDEP") or "",
            "acquirer": (d.get("RESTYPE") or d.get("ACQNAME") or "")[:80],
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "failure_date", "name", "city", "state",
                "assets_m", "deposits_m", "acquirer", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"fdic_bank_watch: {len(rows)} failures -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
