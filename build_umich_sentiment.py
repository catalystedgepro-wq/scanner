#!/usr/bin/env python3
"""build_umich_sentiment.py — U-Michigan consumer sentiment (monthly).

U-Mich Survey of Consumers (preliminary mid-month + final end-month).
Moves broad market + consumer discretionary (TGT, WMT, COST, HD, LOW,
TJX, ROST, BBY, ULTA). Expectations component is leading; current
conditions is coincident.

Source: FRED series UMCSENT (sentiment) + UMCSENT1 (expectations).
Output: umich_sentiment.csv
Columns: month, headline_sentiment, expectations, current_conditions, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "umich_sentiment.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("headline_sentiment", "UMCSENT"),
    ("expectations", "MICH"),
    ("current_conditions", "UMCSENT1"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"umich {sid}: {e}")
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
    return out


def main() -> None:
    data: dict[str, dict[str, float]] = {}
    for alias, sid in SERIES:
        data[alias] = dict(fetch(sid)[-24:])  # last 24 months
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:24]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "headline_sentiment": f"{data['headline_sentiment'].get(d, 0):.1f}",
            "expectations": f"{data['expectations'].get(d, 0):.1f}",
            "current_conditions": f"{data['current_conditions'].get(d, 0):.1f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "headline_sentiment", "expectations",
                "current_conditions", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"umich_sentiment: {len(rows)} months | latest {latest.get('month','?')} "
          f"headline={latest.get('headline_sentiment','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
