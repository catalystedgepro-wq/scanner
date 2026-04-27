#!/usr/bin/env python3
"""build_census_retail.py — US Census Advance Monthly Retail Sales (MARTS).

MARTS is released ~2 weeks after month-end and is the authoritative
snapshot of US retail spending by NAICS sector. Highly market-moving
for the consumer-discretionary / consumer-staples complex:

- **Total (44X72)** surprise > ±0.3 MoM → XRT gaps 1-2%
- **Motor vehicles (441)** weak → F, GM, KMX, AN, LAD pressure
- **Building materials (444)** weak → HD, LOW, BECN, BLDR pressure
- **Food & beverage (445)** strong → KR, SFM, ACI outperform
- **Gasoline (447)** jump → MPC, VLO, PSX pricing-power signal
- **Clothing (448)** strong → GPS, URBN, LULU, TJX, ROST tailwind
- **General merchandise (452)** weak → WMT, TGT, COST risk
- **Nonstore retail (454)** strong → AMZN, CHWY, W, ETSY winners
- **Food services (722)** strong → MCD, SBUX, CMG, DRI, EAT, SHAK
- **Sporting goods (451)** → DKS, HIBB, BBWI

Trade uses:
- Headline beat > +0.5 MoM: long XRT + RCD consumer-discretionary
  ETF for 1-3 session window.
- Nonstore strength divergence vs brick & mortar > +1pt = long AMZN
  short TGT/WMT pair trade.
- Food services weakness → weak restaurant earnings tell; short
  restaurant ETF (EATZ) if >2 consecutive months sub-0.
- Gasoline sales up > +2% MoM = pump-price pass-through → refiner
  margin expansion (MPC/VLO/PSX).

Data economics:
- SM = Seasonally-adjusted Monthly value in $M
- MPCSM = Month-over-Month % change, seasonally-adjusted
- E_SM / E_MPCSM = standard error (for confidence assessment)
- YoY computed directly from SM values 12 months apart

Source: api.census.gov/data/timeseries/eits/marts (free, no key, ~2-3s
median response, stdlib-only).

Output: census_retail.csv
Columns: period, category_code, category_name, value_millions,
mom_pct, yoy_pct, standard_error, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "census_retail.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.census.gov/data/timeseries/eits/marts"

# NAICS codes → human-readable labels (trading-relevant subset)
CATEGORIES = {
    "44X72": "Retail & Food Services Total",
    "44Y72": "Retail & Food Services ex-Motor Vehicles",
    "441":   "Motor Vehicle & Parts Dealers",
    "4411":  "Automobile Dealers",
    "4413":  "Auto Parts & Accessories",
    "442":   "Furniture & Home Furnishings",
    "443":   "Electronics & Appliance Stores",
    "444":   "Building Material & Garden",
    "445":   "Food & Beverage Stores",
    "446":   "Health & Personal Care",
    "447":   "Gasoline Stations",
    "448":   "Clothing & Accessories",
    "451":   "Sporting Goods / Hobby / Books",
    "452":   "General Merchandise Stores",
    "4521":  "Department Stores",
    "453":   "Miscellaneous Store Retailers",
    "454":   "Nonstore Retailers",
    "722":   "Food Services & Drinking Places",
}

START_YEAR = "2024"  # Enough history for YoY calc on latest release


def fetch_category(code: str) -> list[list[str]]:
    params = {
        "get": "cell_value,data_type_code,time_slot_id",
        "time": f"from {START_YEAR}",
        "seasonally_adj": "yes",
        "category_code": code,
        "for": "us:*",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"census_retail: {code} -> {e}")
        return []


def main() -> None:
    rows: list[dict] = []

    for code, label in CATEGORIES.items():
        data = fetch_category(code)
        if len(data) <= 1:
            continue

        # Header: [cell_value, data_type_code, time_slot_id, time,
        #          seasonally_adj, us]
        # Collect by (period, type) pairs.
        by_period: dict[str, dict[str, str]] = {}
        for row in data[1:]:
            if len(row) < 4:
                continue
            val, dtype, _slot, period = row[0], row[1], row[2], row[3]
            by_period.setdefault(period, {})[dtype] = val

        periods = sorted(by_period.keys())
        for i, period in enumerate(periods):
            rec = by_period[period]
            sm = rec.get("SM", "")
            mom = rec.get("MPCSM", "")
            e_sm = rec.get("E_SM", "")

            yoy = ""
            if i >= 12 and sm:
                prev = by_period.get(periods[i - 12], {}).get("SM", "")
                try:
                    sm_f = float(sm)
                    prev_f = float(prev)
                    if prev_f != 0:
                        yoy = f"{((sm_f - prev_f) / prev_f) * 100.0:+.2f}"
                except ValueError:
                    pass

            rows.append({
                "period": period,
                "category_code": code,
                "category_name": label,
                "value_millions": sm,
                "mom_pct": mom,
                "yoy_pct": yoy,
                "standard_error": e_sm,
            })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"census_retail: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["period"], r["category_code"]),
              reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["period", "category_code", "category_name",
                        "value_millions", "mom_pct", "yoy_pct",
                        "standard_error", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Latest-month summary: headline + top winner/loser by MoM
    latest = rows[0]["period"] if rows else "?"
    latest_rows = [r for r in rows if r["period"] == latest]

    def _mom_num(r):
        try:
            return float(r["mom_pct"])
        except (ValueError, TypeError):
            return 0.0

    movers = sorted(latest_rows, key=_mom_num, reverse=True)
    hdr = next(
        (r for r in latest_rows if r["category_code"] == "44X72"),
        None,
    )
    hdr_s = (
        f"headline {hdr['mom_pct']}% MoM ({hdr['yoy_pct']}% YoY)"
        if hdr else "headline ?"
    )
    winner = movers[0] if movers else None
    loser = movers[-1] if movers else None
    win_s = (
        f"best: {winner['category_code']}={winner['mom_pct']}%"
        if winner else ""
    )
    lose_s = (
        f"worst: {loser['category_code']}={loser['mom_pct']}%"
        if loser else ""
    )

    print(f"census_retail: {len(rows)} rows | latest {latest} | "
          f"{hdr_s} | {win_s} | {lose_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
