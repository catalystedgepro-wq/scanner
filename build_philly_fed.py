#!/usr/bin/env python3
"""build_philly_fed.py — Philly Fed Manufacturing Index (monthly).

Philly Fed + Empire State + Chicago PMI = leading industrial activity.
Composite new-orders subindex turns 2-3 months before ISM. Moves MMM,
HON, ETN, GE, CAT, DE, PH, DOV, AME, IR, XYL, FLS, WHR.

Source: FRED PHFPI (headline), GACDISA (Empire State), CHIPMI (Chicago).
Output: philly_fed.csv
Columns: month, philly, empire, chicago_pmi, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "philly_fed.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("philly", "GACDFSA066MSFRBPHI"),
    ("empire", "GACDISA066MSFRBNY"),
    ("chicago", "CHIPMI"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"philly {sid}: {e}")
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
    return out[-48:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    all_dates = set()
    for d in data.values():
        all_dates |= d.keys()
    dates = sorted(all_dates, reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "month": d,
            "philly": f"{data['philly'].get(d, 0):+.1f}",
            "empire": f"{data['empire'].get(d, 0):+.1f}",
            "chicago_pmi": f"{data['chicago'].get(d, 0):.1f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "philly", "empire", "chicago_pmi", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"philly_fed: {len(rows)} months | latest {latest.get('month','?')} "
          f"philly={latest.get('philly','?')} empire={latest.get('empire','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
