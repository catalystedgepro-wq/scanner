#!/usr/bin/env python3
"""build_treasury_mspd.py — Monthly Statement of Public Debt.

US Treasury MSPD table 1: outstanding debt by security type
(Marketable: Bills/Notes/Bonds/TIPS/FRN + Nonmarketable: Series-EE/I,
Government Account Series, etc.).

High-signal readthrough:
- Bills ↑ sharply → Treasury heavy short-end issuance, pressures SOFR
  and bill-bond spread
- Notes/Bonds ↑ → term-premium supply into back of curve
- TIPS ↑ → demand signal for inflation protection
- Intragov holdings → Trust-fund exhaustion progress (SS, Medicare)

Captures last 12 monthly observations (1 year debt-composition tape).

Source: api.fiscaldata.treasury.gov/.../debt/mspd/mspd_table_1
Output: treasury_mspd.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_mspd.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.fiscaldata.treasury.gov/services/api/"
       "fiscal_service/v1/debt/mspd/mspd_table_1"
       "?format=json&page%5Bsize%5D=400&sort=-record_date")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8",
                                                 errors="ignore"))
    except Exception as e:
        print(f"treasury_mspd: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"treasury_mspd: keeping {OUT_CSV.name}")
        return

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        return

    # Keep last 12 months of data.
    dates_seen: list[str] = []
    for row in data:
        rd = row.get("record_date")
        if rd and rd not in dates_seen:
            dates_seen.append(rd)
        if len(dates_seen) >= 12:
            break
    keep_dates = set(dates_seen)
    filtered = [r for r in data if r.get("record_date") in keep_dates]

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for r in filtered:
        try:
            public_bn = float(r.get("debt_held_public_mil_amt", 0)) / 1000
        except (TypeError, ValueError):
            public_bn = 0.0
        try:
            intragov_bn = float(r.get("intragov_hold_mil_amt", 0)) / 1000
        except (TypeError, ValueError):
            intragov_bn = 0.0
        try:
            total_bn = float(r.get("total_mil_amt", 0)) / 1000
        except (TypeError, ValueError):
            total_bn = 0.0
        rows.append({
            "date": r.get("record_date", ""),
            "security_type": (r.get("security_type_desc") or "")[:40],
            "security_class": (r.get("security_class_desc") or "")[:60],
            "public_usd_bn": f"{public_bn:.2f}",
            "intragov_usd_bn": f"{intragov_bn:.2f}",
            "total_usd_bn": f"{total_bn:.2f}",
            "captured_at": now_iso,
        })

    if not rows:
        return

    rows.sort(key=lambda r: (r["date"], r["security_type"],
                             r["security_class"]), reverse=True)

    fieldnames = ["date", "security_type", "security_class",
                  "public_usd_bn", "intragov_usd_bn", "total_usd_bn",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest month, bills vs notes vs bonds.
    latest = rows[0]["date"]
    latest_rows = [r for r in rows if r["date"] == latest]
    by_class = {r["security_class"]: float(r["total_usd_bn"])
                for r in latest_rows if r["security_class"]}
    bills = by_class.get("Bills", 0)
    notes = by_class.get("Notes", 0)
    bonds = by_class.get("Bonds", 0)
    tips = by_class.get(
        "Treasury Inflation-Protected Securities", 0) or by_class.get(
        "TIPS", 0)
    total = sum(by_class.values())
    print(f"treasury_mspd: {len(rows)} rows | latest={latest} | "
          f"total=${total/1000:.2f}T bills=${bills/1000:.2f}T "
          f"notes=${notes/1000:.2f}T bonds=${bonds/1000:.2f}T "
          f"tips=${tips/1000:.2f}T -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
