#!/usr/bin/env python3
"""build_fdic_failures.py — FDIC failed bank list (historical + recent).

Every bank failure = immediate catalyst. SVB/FRC/SBNY 2023 =
KRE/XLF collapse. Flag current failures + near-miss regional banks
(CRE exposure, uninsured deposits). BOK, WAL, PACW, CUBI, ZION, KEY,
CMA, FHN all trade off regional-bank stress.

Source: banks.data.fdic.gov/api/failures (REST, no key).
Output: fdic_failures.csv
Columns: failure_date, bank_name, city, state, total_assets_k,
         total_deposits_k, acquirer, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fdic_failures.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = (
    "https://banks.data.fdic.gov/api/failures?"
    "filters=FAILDATE:[2020-01-01%20TO%20*]"
    "&fields=NAME,CITY,STALP,FAILDATE,RESTYPE,QBFASSET,QBFDEP,SAVR"
    "&limit=500&sort_by=FAILDATE&sort_order=DESC"
)


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fdic: {e}")
        return []
    return [hit.get("data", hit) for hit in (data.get("data") or [])]


def main() -> None:
    items = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for it in items:
        rows.append({
            "failure_date": (it.get("FAILDATE") or "")[:10],
            "bank_name": (it.get("NAME") or "")[:80],
            "city": it.get("CITY", "")[:40],
            "state": it.get("STALP", "")[:2],
            "total_assets_k": it.get("QBFASSET", ""),
            "total_deposits_k": it.get("QBFDEP", ""),
            "acquirer": (it.get("SAVR") or "")[:60],
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["failure_date", "bank_name", "city", "state",
                        "total_assets_k", "total_deposits_k",
                        "acquirer", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fdic: {len(rows)} failures since 2020 | latest "
          f"{latest.get('failure_date','?')} {latest.get('bank_name','?')[:40]} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
