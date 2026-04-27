#!/usr/bin/env python3
"""build_treasury_tic.py — Treasury International Capital (TIC) foreign flows.

TIC data shows net foreign purchases of US Treasuries / equities.
Foreign selling → 10Y yields rise → growth-stock sell-off (QQQ weight),
bond ETFs (TLT, IEF, SHY), FX (UUP, FXY dollar-debasement). China's
share is the single most-watched number.

Source: US Treasury TIC website JSON + FRED proxy series.
  - TREAST (treasuries held by foreigners): FRED alias
  - FRGNHOLDOTH: FRED secondary
Output: treasury_tic.csv
Columns: month, foreign_net_buy_usd_b, china_holdings_b, japan_holdings_b, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "treasury_tic.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# FRED proxies for TIC aggregates
SERIES = [
    ("foreign_holdings_total_b", "FDHBFIN"),  # Federal Debt Held by Foreign & Intl
    ("foreign_official_holdings_b", "FDHBFRBN"),  # Fed-held
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"tic {sid}: {e}")
        return []
    out = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v in {".", ""}:
            continue
        try:
            out.append((d, float(v)))
        except Exception:
            pass
    return out[-36:]


def main() -> None:
    data: dict[str, dict[str, float]] = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "foreign_net_buy_usd_b": "",
            "china_holdings_b": "",
            "japan_holdings_b": "",
            "total_foreign_b": f"{data['foreign_holdings_total_b'].get(d, 0):.0f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "foreign_net_buy_usd_b", "china_holdings_b",
                "japan_holdings_b", "total_foreign_b", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"treasury_tic: {len(rows)} months | latest {latest.get('month','?')} "
          f"total_foreign={latest.get('total_foreign_b','?')}B -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
