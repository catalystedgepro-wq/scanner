#!/usr/bin/env python3
"""build_housing_starts.py — Housing starts + building permits (monthly).

Starts = broke-ground, permits = pipeline (leads starts by 1-2 months).
Drives DHI, LEN, PHM, NVR, TOL, KBH, MTH (homebuilders), BLDR, BCC (LBM),
HD, LOW (big box), LPX, WY (lumber/timber), SHW, PPG (paint), USG (drywall).

Source: FRED HOUST (starts SAAR), PERMIT (permits SAAR).
Output: housing_starts.csv
Columns: month, starts_saar_k, permits_saar_k, starts_yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "housing_starts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [("starts", "HOUST"), ("permits", "PERMIT")]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"housing {sid}: {e}")
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
    starts = dict(fetch("HOUST"))
    permits = dict(fetch("PERMIT"))
    dates = sorted(set(starts) | set(permits), reverse=True)[:36]
    all_sorted = sorted(starts.keys())
    idx = {d: i for i, d in enumerate(all_sorted)}
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        s = starts.get(d, 0)
        i = idx.get(d, -1)
        prev = starts.get(all_sorted[i - 12], 0) if i >= 12 else 0
        yoy = f"{((s / prev - 1) * 100):.2f}" if prev else ""
        rows.append({
            "month": d,
            "starts_saar_k": f"{s:.0f}",
            "permits_saar_k": f"{permits.get(d, 0):.0f}",
            "starts_yoy_pct": yoy,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "starts_saar_k", "permits_saar_k",
                "starts_yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"housing_starts: {len(rows)} months | latest {latest.get('month','?')} "
          f"starts={latest.get('starts_saar_k','?')}k permits={latest.get('permits_saar_k','?')}k "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
