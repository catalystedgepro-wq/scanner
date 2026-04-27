#!/usr/bin/env python3
"""build_comtrade_flows.py — UN Comtrade US bilateral trade flows.

Annual US trade flows by commodity (HS chapter) + partner country:
- Exports to top partners (China, Mexico, Canada, EU, UK, Japan)
- Imports from same
- Delta vs prior year → tariff-impact indicator

Signal: re-routing between partners post-tariff rewires whole sectors.
Mexican auto exports ↑ while Chinese ↓ = USMCA lock-in. Commodity
exports (soy/corn/cotton) depend on China policy cycle.

Drives:
- Container shipping (MATX, ZIM, GSL, DAC)
- US agri exporters (ADM, BG, TSN)
- US-Mexico reshoring (ORLY, GM, F, MGA, SUP)
- Base metal importers (STLD, NUE, X)
- China export sentiment (YINN, FXI, MCHI, BABA, PDD, JD)

Source: comtradeapi.un.org/public/v1/preview (free, no key,
500 rows/hour per partner).
Output: comtrade_flows.csv
Columns: reporter, partner, year, flow, hs_chapter, trade_value_usd,
         net_weight_kg, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "comtrade_flows.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# US as reporter; top partners by flow relevance.
# Comtrade partner codes: 0=World, 156=China, 484=Mexico, 124=Canada,
# 276=Germany, 826=UK, 392=Japan, 410=Korea, 704=Vietnam, 356=India.
PARTNERS = [
    (156, "China"),
    (484, "Mexico"),
    (124, "Canada"),
    (276, "Germany"),
    (826, "UK"),
    (392, "Japan"),
    (410, "Korea"),
    (704, "Vietnam"),
]
FLOWS = [("X", "export"), ("M", "import")]
YEAR = dt.datetime.now(dt.timezone.utc).year - 1  # last-completed year


def _fetch(partner: int, flow: str) -> list[dict] | None:
    qs = urllib.parse.urlencode({
        "reporterCode": 842,
        "period": YEAR,
        "cmdCode": "TOTAL",
        "flowCode": flow,
        "partnerCode": partner,
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
        "maxRecords": 5,
    }, safe="")
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"comtrade_flows: p={partner} f={flow}: {e}")
        return None
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    return None


def main() -> None:
    rows: list[dict] = []
    for partner_code, partner_name in PARTNERS:
        for flow_code, flow_name in FLOWS:
            data = _fetch(partner_code, flow_code)
            if not data:
                time.sleep(1)
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    value = float(item.get("primaryValue") or 0)
                except (TypeError, ValueError):
                    value = 0.0
                try:
                    weight = float(item.get("netWgt") or 0)
                except (TypeError, ValueError):
                    weight = 0.0
                rows.append({
                    "reporter": "US",
                    "partner": partner_name,
                    "year": str(YEAR),
                    "flow": flow_name,
                    "hs_chapter": str(item.get("cmdCode") or "")[:8],
                    "trade_value_usd": f"{value:.2f}",
                    "net_weight_kg": f"{weight:.0f}",
                })
            time.sleep(4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"comtrade_flows: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["reporter", "partner", "year", "flow", "hs_chapter",
                  "trade_value_usd", "net_weight_kg", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    exports = [r for r in rows if r["flow"] == "export"
               and r["partner"] != "World"]
    imports = [r for r in rows if r["flow"] == "import"
               and r["partner"] != "World"]
    top_x = max(exports, key=lambda r: float(r["trade_value_usd"]),
                default=None)
    top_m = max(imports, key=lambda r: float(r["trade_value_usd"]),
                default=None)
    bits = []
    if top_x:
        bits.append(f"top_X={top_x['partner']}"
                    f"=${float(top_x['trade_value_usd'])/1e9:.1f}B")
    if top_m:
        bits.append(f"top_M={top_m['partner']}"
                    f"=${float(top_m['trade_value_usd'])/1e9:.1f}B")
    print(f"comtrade_flows: {len(rows)} rows | year {YEAR} | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
