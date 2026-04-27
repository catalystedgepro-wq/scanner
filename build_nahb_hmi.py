#!/usr/bin/env python3
"""build_nahb_hmi.py — NAHB Housing Market Index (monthly).

Homebuilder sentiment leads single-family starts 3-6 months. Moves DHI,
LEN, PHM, TOL, NVR, KBH, MTH. Also whoosh through XHB ETF, and
appliance/materials names MAS, BLDR, LOW, HD. Below 50 = contraction.

Source: FRED NAHBSI (single-family HMI).
Output: nahb_hmi.csv
Columns: month, hmi_index, hmi_mom, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nahb_hmi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"nahb {sid}: {e}")
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
    hmi = dict(fetch("NAHBSI"))
    sorted_dates = sorted(hmi.keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(hmi.keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = hmi.get(d, 0)
        i = idx.get(d, -1)
        prev = hmi.get(sorted_dates[i - 1], 0) if i >= 1 else 0
        rows.append({
            "month": d,
            "hmi_index": f"{cur:.0f}",
            "hmi_mom": f"{(cur - prev):+.0f}" if prev else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["month", "hmi_index", "hmi_mom", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"nahb: {len(rows)} months | latest {latest.get('month','?')} "
          f"hmi={latest.get('hmi_index','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
