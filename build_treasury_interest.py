#!/usr/bin/env python3
"""build_treasury_interest.py — Treasury avg interest rate on debt.

Monthly weighted average interest rate the US Treasury pays on its
outstanding marketable + non-marketable debt. Distinct from TGA
(treasury_fiscal), MTS (treasury_mts), and H.15 curve (treasury_fx):
this is the effective cost of debt service.

Drives:
- Bank NIM backdrop (JPM, BAC, WFC, C, USB)
- Debt-service % of GDP (fiscal sustainability proxy)
- REIT debt cost floors (AMT, CCI, EQIX, WELL, SPG)
- Utilities regulated rate base (SO, DUK, NEE, AEP)
- IG corporate refi burden (MA, V card-network spreads compress)

Signal: trend in marketable avg rate flags refi timing; gap between
Bills vs Bonds reveals curve-adjusted servicing cost.

Source: api.fiscaldata.treasury.gov (free, no key).
Output: treasury_interest.csv
Columns: record_date, security_type, security_desc, avg_rate,
         fiscal_year, fiscal_quarter, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_interest.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://api.fiscaldata.treasury.gov/services/api/"
        "fiscal_service/v2/accounting/od/avg_interest_rates")


def main() -> None:
    qs = urllib.parse.urlencode({
        "sort": "-record_date",
        "page[size]": "240",
    }, safe=":-,")
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"treasury_interest: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_interest: keeping existing {OUT_CSV.name}")
        return

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_interest: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            rate = float(item.get("avg_interest_rate_amt") or 0)
        except (TypeError, ValueError):
            continue
        rows.append({
            "record_date": str(item.get("record_date") or "")[:10],
            "security_type": str(item.get("security_type_desc") or "")[:24],
            "security_desc": str(item.get("security_desc") or "")[:40],
            "avg_rate": f"{rate:.3f}",
            "fiscal_year": str(item.get("record_fiscal_year") or "")[:4],
            "fiscal_quarter": str(item.get("record_fiscal_quarter") or "")[:1],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_interest: parsed 0, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["record_date"], r["security_desc"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["record_date", "security_type", "security_desc",
                  "avg_rate", "fiscal_year", "fiscal_quarter",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_date = rows[0]["record_date"]
    latest = [r for r in rows if r["record_date"] == latest_date]
    bills = next((r for r in latest if "Bills" in r["security_desc"]),
                 None)
    notes = next((r for r in latest if "Notes" in r["security_desc"]),
                 None)
    bonds = next((r for r in latest if "Bonds" in r["security_desc"]),
                 None)
    ttl = next((r for r in latest
                if "Total Marketable" in r["security_desc"]), None)
    bits = []
    for label, r in [("Bills", bills), ("Notes", notes),
                     ("Bonds", bonds), ("TotMkt", ttl)]:
        if r:
            bits.append(f"{label}={r['avg_rate']}%")
    print(f"treasury_interest: {len(rows)} rows | {latest_date} | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
