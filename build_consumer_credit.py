#!/usr/bin/env python3
"""build_consumer_credit.py — G.19 consumer credit + savings rate (monthly).

Revolving credit growth + savings rate = consumer firepower gauge. High
credit + low savings = late-cycle blowup risk (COF, SYF, DFS, AXP, SOFI,
UPST, AFRM). Rising savings = defensive (MCD, PEP, COST sticky-demand).

Source: FRED
  - TOTALSL: Total consumer credit (incl auto + student)
  - REVOLSL: Revolving (credit cards)
  - PSAVERT: Personal savings rate
Output: consumer_credit.csv
Columns: month, total_sl_b, revolving_sl_b, savings_rate_pct,
         revolving_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "consumer_credit.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("total_sl", "TOTALSL"),
    ("revolving_sl", "REVOLSL"),
    ("savings_rate", "PSAVERT"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"cc {sid}: {e}")
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
    rev_sorted = sorted(data["revolving_sl"].keys())
    idx = {d: i for i, d in enumerate(rev_sorted)}
    dates = sorted(data["total_sl"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rev = data["revolving_sl"].get(d, 0)
        i = idx.get(d, -1)
        yoy = data["revolving_sl"].get(rev_sorted[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "total_sl_b": f"{data['total_sl'].get(d, 0) / 1e3:.0f}",
            "revolving_sl_b": f"{rev / 1e3:.0f}",
            "savings_rate_pct": f"{data['savings_rate'].get(d, 0):.1f}",
            "revolving_yoy_pct": f"{((rev / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "total_sl_b", "revolving_sl_b",
                "savings_rate_pct", "revolving_yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"consumer_credit: {len(rows)} months | latest {latest.get('month','?')} "
          f"rev=${latest.get('revolving_sl_b','?')}B sav={latest.get('savings_rate_pct','?')}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
