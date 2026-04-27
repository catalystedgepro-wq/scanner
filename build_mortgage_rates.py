#!/usr/bin/env python3
"""build_mortgage_rates.py — Freddie Mac PMMS mortgage rates (weekly).

30yr mortgage = homebuilder and RE demand gauge. Each 50bp drop below
7% unlocks ~$80B/yr refi volume → ROKT, RKT, UWMC, ZG, Z surge. Below
6% = homebuilder melt-up (DHI, LEN, PHM). Above 7.5% = freeze.

Source: FRED MORTGAGE30US, MORTGAGE15US, MORTGAGE5US.
Output: mortgage_rates.csv
Columns: week, rate_30yr, rate_15yr, rate_5_1arm, rate_30yr_mom, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "mortgage_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("rate_30yr", "MORTGAGE30US"),
    ("rate_15yr", "MORTGAGE15US"),
    ("rate_5_1arm", "MORTGAGE5US"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"mortgage {sid}: {e}")
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
    return out[-120:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    sorted_dates = sorted(data["rate_30yr"].keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(data["rate_30yr"].keys(), reverse=True)[:104]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["rate_30yr"].get(d, 0)
        i = idx.get(d, -1)
        prev = data["rate_30yr"].get(sorted_dates[i - 4], 0) if i >= 4 else 0
        rows.append({
            "week": d,
            "rate_30yr": f"{cur:.2f}",
            "rate_15yr": f"{data['rate_15yr'].get(d, 0):.2f}",
            "rate_5_1arm": f"{data['rate_5_1arm'].get(d, 0):.2f}",
            "rate_30yr_mom": f"{(cur - prev):+.2f}" if prev else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week", "rate_30yr", "rate_15yr",
                "rate_5_1arm", "rate_30yr_mom", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"mortgage: {len(rows)} weeks | latest {latest.get('week','?')} "
          f"30yr={latest.get('rate_30yr','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
