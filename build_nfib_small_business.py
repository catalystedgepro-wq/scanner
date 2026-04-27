#!/usr/bin/env python3
"""build_nfib_small_business.py — NFIB small business optimism (monthly).

Small business = 44% of GDP, 48% of employment. NFIB SBOI leads SMB
hiring 3-6 months. Moves PAYX, ADP, INTU (QuickBooks), small regional
banks (FITB, RF, CFG), Main Street suppliers (TSCO, POOL, GWW).

Source: FRED NFIBSBOI (optimism index).
Output: nfib_small_business.csv
Columns: month, sboi_index, sboi_mom, sboi_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nfib_small_business.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"nfib {sid}: {e}")
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
    sboi = dict(fetch("NFIBSBOI"))
    sorted_dates = sorted(sboi.keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(sboi.keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = sboi.get(d, 0)
        i = idx.get(d, -1)
        prev = sboi.get(sorted_dates[i - 1], 0) if i >= 1 else 0
        yoy = sboi.get(sorted_dates[i - 12], 0) if i >= 12 else 0
        rows.append({
            "month": d,
            "sboi_index": f"{cur:.1f}",
            "sboi_mom": f"{(cur - prev):+.1f}" if prev else "",
            "sboi_yoy_pct": f"{((cur / yoy - 1) * 100):.2f}" if yoy else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "sboi_index", "sboi_mom", "sboi_yoy_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"nfib: {len(rows)} months | latest {latest.get('month','?')} "
          f"sboi={latest.get('sboi_index','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
