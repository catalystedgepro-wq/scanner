#!/usr/bin/env python3
"""build_treasury_sales.py — monthly Treasury securities sales mix.

Monthly gross+net sales of US Treasury securities by type:
- EE Savings Bond (retail safe-money flow)
- I Savings Bond (inflation-hedge retail demand — surged 2022-2023)
- Marketable (Bills/Notes/Bonds/TIPS retail purchases via TreasuryDirect)

Signal: I-bond net sales spiking flags retail inflation panic / yield-
hunt. Combined with CPI/MTS, reveals demand-side response to real
rates. Drops when real rates turn positive → marginal retail flows
pivot back to equities.

Drives:
- Money-market / short-duration ETFs (SGOV, BIL, ICSH, FLOT)
- Retail broker flows (SCHW, IBKR, HOOD)
- Banking deposit competition intensity (JPM, WFC, USB)

Source: api.fiscaldata.treasury.gov (free, no key).
Output: treasury_sales.csv
Columns: record_date, security_type, security_class, sold_cnt,
         gross_sales, net_sales, fiscal_quarter, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_sales.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://api.fiscaldata.treasury.gov/services/api/"
        "fiscal_service/v1/accounting/od/securities_sales")


def main() -> None:
    qs = urllib.parse.urlencode({
        "sort": "-record_date",
        "page[size]": "180",
    }, safe=":-,")
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"treasury_sales: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_sales: keeping existing {OUT_CSV.name}")
        return

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_sales: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            gross = float(item.get("gross_sales_amt") or 0)
            net = float(item.get("net_sales_amt") or 0)
        except (TypeError, ValueError):
            continue
        rows.append({
            "record_date": str(item.get("record_date") or "")[:10],
            "security_type": str(item.get("security_type_desc") or "")[:20],
            "security_class": str(item.get("security_class_desc") or "")[:10],
            "sold_cnt": str(item.get("securities_sold_cnt") or 0)[:10],
            "gross_sales": f"{gross:.2f}",
            "net_sales": f"{net:.2f}",
            "fiscal_quarter": str(item.get("record_fiscal_quarter") or "")[:1],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_sales: 0 rows, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["record_date"], r["security_class"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["record_date", "security_type", "security_class",
                  "sold_cnt", "gross_sales", "net_sales",
                  "fiscal_quarter", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_date = rows[0]["record_date"]
    latest = [r for r in rows if r["record_date"] == latest_date]
    ibond = next((r for r in latest if r["security_class"] == "I"), None)
    eebond = next((r for r in latest if r["security_class"] == "EE"), None)
    bits = []
    if ibond:
        bits.append(f"I-bond_net=${float(ibond['net_sales'])/1e6:.1f}M")
    if eebond:
        bits.append(f"EE-bond_net=${float(eebond['net_sales'])/1e6:.1f}M")
    print(f"treasury_sales: {len(rows)} rows | {latest_date} | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
