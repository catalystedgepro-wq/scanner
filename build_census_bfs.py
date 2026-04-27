#!/usr/bin/env python3
"""build_census_bfs.py — Census Business Formation Statistics.

BFS tracks new-business applications filed with the IRS (EIN requests),
broken down by NAICS sector. It's a leading indicator for:

- **Small-business lending demand**: high-propensity applications
  (BA_HBA) signal borrower pipeline for SBA lenders (TCBI, LIVE, BANC,
  WAL, PNFP, CUBI).
- **Payroll-tech TAM growth**: projected business formations (BF_PBF4Q)
  feed PAYX, PCTY, PAYC, ADP, INTU (QuickBooks), HRB addressable market.
- **Sector rotation signal**: NAICS23 construction BFS rising → HD, LOW,
  BLDR, BECN demand pull-through. NAICS72 accommodation/food rising →
  SYSCO (SYY), US Foods (USFD), CMG, CAKE traffic.
- **Commercial-real-estate bid** (NAICS53): office/retail demand for
  leasing → CBRE, CWK, JLL.
- **Gig-economy volume**: NAICS48-49 transport self-employed → UBER,
  LYFT, DASH driver supply.

Metrics (all seasonally adjusted, monthly):
- `BA_BA`    — All Business Applications (broadest)
- `BA_HBA`   — High-Propensity BAs (likely-to-have-payroll subset)
- `BA_CBA`   — Corporation Business Applications (C-corps & LLCs)
- `BA_WBA`   — BAs with Planned Wages (strongest startup signal)
- `BF_PBF4Q` — Projected Business Formations within 4 quarters
- `BF_PBF8Q` — Projected Business Formations within 8 quarters
- `BF_SBF4Q` — Spliced (historical+projected) BFs within 4q
- `BF_SBF8Q` — Spliced BFs within 8q

Trade uses:
- BA_WBA MoM > +3% → gig/labor expansion, bullish UBER/DASH/ADP.
- BA_HBA NAICS23 YoY turning positive → early cycle housing bid
  (HD, LOW, BLDR, BECN, 1-2q forward).
- BF_PBF8Q rising 2+ quarters → small-biz software TAM expanding,
  bullish INTU, PAYC, BILL, HUBS.

Source: api.census.gov/data/timeseries/eits/bfs (free, no key,
stdlib only). Released monthly, ~3 weeks after month-end.

Output: census_bfs.csv
Columns: period, category_code, category_name, ba_ba, ba_hba, ba_cba,
ba_wba, bf_pbf4q, bf_pbf8q, bf_sbf4q, bf_sbf8q, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_bfs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.census.gov/data/timeseries/eits/bfs"

# Trading-relevant NAICS sectors + TOTAL headline.
CATEGORIES = {
    "TOTAL":   "All Industries (Headline)",
    "NAICS11": "Agriculture / Forestry / Fishing",
    "NAICS21": "Mining / Oil & Gas Extraction",
    "NAICS22": "Utilities",
    "NAICS23": "Construction",
    "NAICS31-33": "Manufacturing",
    "NAICS42": "Wholesale Trade",
    "NAICS44-45": "Retail Trade",
    "NAICS48-49": "Transportation / Warehousing",
    "NAICS51": "Information / Media / Tech",
    "NAICS52": "Finance & Insurance",
    "NAICS53": "Real Estate / Rental / Leasing",
    "NAICS54": "Professional / Scientific / Technical",
    "NAICS55": "Management of Companies",
    "NAICS56": "Administrative / Support / Waste",
    "NAICS61": "Educational Services",
    "NAICS62": "Health Care / Social Assistance",
    "NAICS71": "Arts / Entertainment / Recreation",
    "NAICS72": "Accommodation / Food Services",
    "NAICS81": "Other Services",
}

METRICS = ["BA_BA", "BA_HBA", "BA_CBA", "BA_WBA",
           "BF_PBF4Q", "BF_PBF8Q", "BF_SBF4Q", "BF_SBF8Q"]


def fetch_category(code: str) -> list[list[str]]:
    params = {
        "get": "cell_value,data_type_code,time_slot_id",
        "time": "from 2024",
        "seasonally_adj": "yes",
        "category_code": code,
        "for": "us:*",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status == 204:
                return []
            body = r.read().decode("utf-8", errors="ignore").strip()
            if not body:
                return []
            return json.loads(body)
    except Exception as e:
        print(f"census_bfs: {code} -> {e}")
        return []


def main() -> None:
    rows: list[dict] = []

    for code, label in CATEGORIES.items():
        data = fetch_category(code)
        if len(data) <= 1:
            continue

        # Header shape: [cell_value, data_type_code, time_slot_id,
        #                time, seasonally_adj, category_code, us]
        by_period: dict[str, dict[str, str]] = {}
        for row in data[1:]:
            if len(row) < 4:
                continue
            val, dtype, _slot, period = row[0], row[1], row[2], row[3]
            by_period.setdefault(period, {})[dtype] = val

        for period in sorted(by_period.keys()):
            rec = by_period[period]
            rows.append({
                "period": period,
                "category_code": code,
                "category_name": label,
                "ba_ba":     rec.get("BA_BA", ""),
                "ba_hba":    rec.get("BA_HBA", ""),
                "ba_cba":    rec.get("BA_CBA", ""),
                "ba_wba":    rec.get("BA_WBA", ""),
                "bf_pbf4q":  rec.get("BF_PBF4Q", ""),
                "bf_pbf8q":  rec.get("BF_PBF8Q", ""),
                "bf_sbf4q":  rec.get("BF_SBF4Q", ""),
                "bf_sbf8q":  rec.get("BF_SBF8Q", ""),
            })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"census_bfs: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["period"], r["category_code"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["period", "category_code", "category_name",
                  "ba_ba", "ba_hba", "ba_cba", "ba_wba",
                  "bf_pbf4q", "bf_pbf8q", "bf_sbf4q", "bf_sbf8q",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]["period"] if rows else "?"
    total_now = next(
        (r for r in rows
         if r["period"] == latest and r["category_code"] == "TOTAL"),
        None,
    )
    if total_now:
        hdr = (f"TOTAL: BA_BA={total_now['ba_ba']}, "
               f"BA_HBA={total_now['ba_hba']} (high-propensity), "
               f"BA_WBA={total_now['ba_wba']} (planned-wages), "
               f"BF_PBF8Q={total_now['bf_pbf8q']}")
    else:
        hdr = "headline ?"

    print(f"census_bfs: {len(rows)} rows | latest {latest} | "
          f"{hdr} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
