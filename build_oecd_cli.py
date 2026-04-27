#!/usr/bin/env python3
"""build_oecd_cli.py — OECD Composite Leading Indicators.

Leading economic activity 6-9 months ahead of GDP prints. CLI > 100
and rising = expansion; < 100 and falling = contraction. Country-
specific CLIs catalyze regional ETF flows.

Affected instruments:
- USA CLI down: SPY QQQ IWM (US equity drag), TLT bid
- China CLI up: FXI MCHI YINN ASHR (China re-rating), LIT lithium
- EA CLI down: EWG EWQ EWI (Euro bloc drag)
- Japan CLI up: EWJ DXJ (Japan reflation)
- Global CLI turning: EEM ACWI (global cyclicals)

Source: FRED fredgraph.csv (OECD data, monthly, 2-month lag).
Output: oecd_cli.csv
Columns: date, us, china, japan, eurozone, global, us_direction, glob_direction
"""
from __future__ import annotations
import csv
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "oecd_cli.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = {
    "us": "USALOLITOAASTSAM",
    "china": "CHNLOLITOAASTSAM",
    "japan": "JPNLOLITOAASTSAM",
    "eurozone": "EA19LOLITOAASTSAM",
    "global": "OECDLOLITOAASTSAM",
}


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    out: list[tuple[str, float]] = []
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"oecd {sid}: {e}")
        return out
    for line in body.splitlines()[1:]:
        if "," not in line:
            continue
        date, val = line.split(",", 1)
        val = val.strip()
        if val in (".", "", "NaN"):
            continue
        try:
            out.append((date.strip(), float(val)))
        except ValueError:
            continue
    return out


def direction(series: list[tuple[str, float]]) -> str:
    if len(series) < 4:
        return ""
    latest = series[-1][1]
    three_ago = series[-4][1]
    if latest > 100 and latest > three_ago:
        return "EXPANSION_UP"
    if latest > 100 and latest < three_ago:
        return "EXPANSION_SLOWING"
    if latest < 100 and latest > three_ago:
        return "CONTRACTION_BOTTOMING"
    if latest < 100 and latest < three_ago:
        return "CONTRACTION_DEEPENING"
    return ""


def main() -> None:
    data = {k: fetch(v) for k, v in SERIES.items()}
    all_dates = set()
    for series in data.values():
        all_dates.update(d for d, _ in series)
    sorted_dates = sorted(all_dates, reverse=True)[:36]  # 3 yrs monthly

    # Convert lists to dicts for lookup
    lookups = {k: dict(v) for k, v in data.items()}
    us_dir = direction(data["us"])
    glob_dir = direction(data["global"])

    rows: list[dict] = []
    for date in sorted_dates:
        rows.append({
            "date": date,
            "us": f"{lookups['us'].get(date, ''):.2f}"
                if date in lookups["us"] else "",
            "china": f"{lookups['china'].get(date, ''):.2f}"
                if date in lookups["china"] else "",
            "japan": f"{lookups['japan'].get(date, ''):.2f}"
                if date in lookups["japan"] else "",
            "eurozone": f"{lookups['eurozone'].get(date, ''):.2f}"
                if date in lookups["eurozone"] else "",
            "global": f"{lookups['global'].get(date, ''):.2f}"
                if date in lookups["global"] else "",
            "us_direction": us_dir if date == sorted_dates[0] else "",
            "glob_direction": glob_dir if date == sorted_dates[0] else "",
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "us", "china", "japan", "eurozone",
                        "global", "us_direction", "glob_direction"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"oecd_cli: {len(rows)} months | latest {latest.get('date','?')} "
          f"US={latest.get('us','?')} CN={latest.get('china','?')} "
          f"Global={latest.get('global','?')} | regime={us_dir}/{glob_dir} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
