#!/usr/bin/env python3
"""build_nyfed_sofr.py — NY Fed SOFR repo-market stress tracker (30d).

SOFR (Secured Overnight Financing Rate) is the benchmark for $ trillions
in derivatives, mortgages, and corporate loans. Daily reading from the
tri-party repo market — the plumbing that funds Treasury collateral.

Signals:
- SOFR vs Fed target range upper bound: spread > 0 = repo stress,
  indicates dealer balance-sheet is choked. Classic year-end or
  quarter-end window-dressing spike → risk-off for equities, bid for
  short-term Treasuries.
- Volume surge > 1 std above 30d avg: demand for repo funding is high,
  often precedes equity selloff (dealers pulling in, de-risking).
- Percentile spread (99th − 1st): dispersion spike = market fracturing,
  some counterparties paying much higher than others → stress warning.

Source: markets.newyorkfed.org/api/rates/secured/sofr/last/30.json
(free, no key, JSON array of last 30 business days).

Output: nyfed_sofr.csv
Columns: date, sofr_pct, volume_usd_billions, pctile_1, pctile_25,
         pctile_75, pctile_99, pctile_spread, revised, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nyfed_sofr.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/30.json"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nyfed_sofr: {e}")
        return []
    return body.get("refRates", []) or []


def main() -> None:
    rates = fetch()
    if not rates and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"nyfed_sofr: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for r in rates:
        date = r.get("effectiveDate", "")
        pct = r.get("percentRate")
        if not date or pct is None:
            continue
        p1 = r.get("percentPercentile1") or 0
        p99 = r.get("percentPercentile99") or 0
        spread = round(float(p99) - float(p1), 3)
        rows.append({
            "date": date,
            "sofr_pct": f"{float(pct):.3f}",
            "volume_usd_billions": f"{float(r.get('volumeInBillions', 0) or 0):.0f}",
            "pctile_1": f"{float(p1):.3f}",
            "pctile_25": f"{float(r.get('percentPercentile25', 0) or 0):.3f}",
            "pctile_75": f"{float(r.get('percentPercentile75', 0) or 0):.3f}",
            "pctile_99": f"{float(p99):.3f}",
            "pctile_spread": f"{spread:.3f}",
            "revised": r.get("revisionIndicator") or "",
        })

    rows.sort(key=lambda r: r["date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["date", "sofr_pct", "volume_usd_billions", "pctile_1",
                  "pctile_25", "pctile_75", "pctile_99", "pctile_spread",
                  "revised", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    if rows:
        latest = rows[0]
        avg_vol = (sum(float(r["volume_usd_billions"]) for r in rows)
                   / len(rows))
        print(f"nyfed_sofr: {len(rows)} days | latest "
              f"{latest['date']} {latest['sofr_pct']}% "
              f"vol=${latest['volume_usd_billions']}B "
              f"(30d avg ${avg_vol:.0f}B) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
