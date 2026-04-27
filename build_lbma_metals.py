#!/usr/bin/env python3
"""build_lbma_metals.py — LBMA daily precious-metal fixings.

The London Bullion Market Association sets the global benchmark fix
for gold (AM/PM), silver, platinum, palladium (AM/PM).  These are
the reference prices used by:
- Central bank reserve valuations
- GLD/SLV/PPLT/PALL ETF NAVs
- Miner revenue guidance (NEM, GOLD, WPM, FNV, PAAS)
- Industrial metals (catalytic converters: PGMs)

Each fix is published in USD, GBP, EUR — we capture USD and compute
day-over-day percent move to surface break-outs.

Source: prices.lbma.org.uk/json/{gold_am,gold_pm,silver,
        platinum_am,palladium_pm}.json
Output: lbma_metals.csv

Signal:
- Gold PM > AM + rising → risk-off momentum (SPY down day)
- Silver > gold % move → industrial PM rotation
- Platinum/palladium split → auto-catalyst vs. jewelry rotation
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "lbma_metals.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEEDS = {
    "gold_pm": "https://prices.lbma.org.uk/json/gold_pm.json",
    "gold_am": "https://prices.lbma.org.uk/json/gold_am.json",
    "silver": "https://prices.lbma.org.uk/json/silver.json",
    "platinum_pm": "https://prices.lbma.org.uk/json/platinum_pm.json",
    "palladium_pm": "https://prices.lbma.org.uk/json/palladium_pm.json",
}
LOOKBACK_DAYS = 60


def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"lbma_metals: {url[-15:]}: {e}")
        return None


def _parse(payload: object) -> list[tuple[str, float]]:
    if not isinstance(payload, list):
        return []
    cutoff = dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)
    out: list[tuple[str, float]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        d = entry.get("d")
        v = entry.get("v")
        if not d or not isinstance(v, list) or not v:
            continue
        try:
            date = dt.date.fromisoformat(d)
        except Exception:
            continue
        if date < cutoff:
            continue
        usd = v[0] if v else None
        if not isinstance(usd, (int, float)):
            continue
        out.append((d, float(usd)))
    return out


def main() -> None:
    series: dict[str, dict[str, float]] = {}
    for name, url in FEEDS.items():
        series[name] = dict(_parse(_get_json(url)))

    all_dates = sorted({d for s in series.values() for d in s},
                       reverse=True)
    if not all_dates:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"lbma_metals: no fetch, keeping {OUT_CSV.name}")
        return

    # Compute day-over-day % change per metric.
    prev_by_metric: dict[str, float] = {}
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []

    # Iterate chronological for correct pct-change; emit reversed.
    for d in sorted(all_dates):
        row: dict[str, str] = {"date": d, "captured_at": now_iso}
        for metric in FEEDS:
            v = series[metric].get(d)
            row[metric] = f"{v:.2f}" if v is not None else ""
            prev = prev_by_metric.get(metric)
            if v is not None and prev is not None and prev > 0:
                pct = (v - prev) / prev * 100.0
                row[f"{metric}_chg_pct"] = f"{pct:+.2f}"
            else:
                row[f"{metric}_chg_pct"] = ""
            if v is not None:
                prev_by_metric[metric] = v
        rows.append(row)

    rows.reverse()
    fieldnames = ["date"]
    for metric in FEEDS:
        fieldnames.append(metric)
        fieldnames.append(f"{metric}_chg_pct")
    fieldnames.append("captured_at")

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    print(f"lbma_metals: {len(rows)} days | latest={latest['date']} "
          f"gold_pm={latest.get('gold_pm')} "
          f"({latest.get('gold_pm_chg_pct')}%) "
          f"silver={latest.get('silver')} "
          f"({latest.get('silver_chg_pct')}%) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
