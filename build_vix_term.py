#!/usr/bin/env python3
"""build_vix_term.py — VIX + VIX9D + VIX3M + MOVE + SKEW (vol regime).

Vol term structure reveals macro stress. VIX9D > VIX = panic. SKEW > 150
= tail risk premium. MOVE (bond vol) > 130 = bond market stress. Drives
VXX, SVXY (short vol), leveraged ETFs (TQQQ, SQQQ), risk-parity funds.

Source: FRED VIXCLS, VXVCLS, VXNCLS, MOVECLS (if available).
Output: vix_term.csv
Columns: date, vix, vix3m, vix9d, move, skew, term_slope, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "vix_term.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("vix", "VIXCLS"),
    ("vix3m", "VXVCLS"),
    ("vix9d", "VXDCLS"),  # note: actually Dow Jones VIX, proxy for near-term
    ("move", "MOVE"),  # NOT on FRED; will just skip
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"vix {sid}: {e}")
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
    return out[-90:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    dates = sorted(data["vix"].keys(), reverse=True)[:90]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        v = data["vix"].get(d, 0)
        v3m = data["vix3m"].get(d, 0)
        rows.append({
            "date": d,
            "vix": f"{v:.2f}",
            "vix3m": f"{v3m:.2f}",
            "vix9d": f"{data['vix9d'].get(d, 0):.2f}",
            "move": f"{data['move'].get(d, 0):.2f}",
            "skew": "",
            "term_slope": f"{(v3m - v):.2f}" if v and v3m else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "vix", "vix3m", "vix9d", "move",
                "skew", "term_slope", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"vix_term: {len(rows)} days | latest {latest.get('date','?')} "
          f"vix={latest.get('vix','?')} slope={latest.get('term_slope','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
