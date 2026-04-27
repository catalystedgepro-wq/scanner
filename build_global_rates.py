#!/usr/bin/env python3
"""build_global_rates.py — Global central bank rates (monthly).

Global policy rate divergence = FX driver. ECB/BOE hawkish + Fed
dovish = USD down, EEM rally, commodities up (XLE, XME, FCX, BHP).
BOJ hike = USDJPY dive, carry-trade unwind (risk-off). China LPR cut
= CN50, BABA, KWEB rally.

Source: FRED ECBMLFR (ECB main), IUDSOIA (BOE bank rate),
IRSTCI01JPM156N (Japan policy rate), INTDSRCNM193N (China 1yr lending).
Output: global_rates.csv
Columns: month, ecb, boe, boj, china_1yr, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "global_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("ecb", "ECBMLFR"),
    ("boe", "IUDSOIA"),
    ("boj", "IRSTCI01JPM156N"),
    ("china_1yr", "INTDSRCNM193N"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"global_rates {sid}: {e}")
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
    return out[-60:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    all_dates: set[str] = set()
    for d in data.values():
        all_dates |= d.keys()
    dates = sorted(all_dates, reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "ecb": f"{data['ecb'].get(d, 0):.2f}" if data['ecb'].get(d) else "",
            "boe": f"{data['boe'].get(d, 0):.2f}" if data['boe'].get(d) else "",
            "boj": f"{data['boj'].get(d, 0):.3f}" if data['boj'].get(d) else "",
            "china_1yr": f"{data['china_1yr'].get(d, 0):.2f}" if data['china_1yr'].get(d) else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "ecb", "boe", "boj", "china_1yr", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"global_rates: {len(rows)} months | latest {latest.get('month','?')} "
          f"ecb={latest.get('ecb','?')} boe={latest.get('boe','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
