#!/usr/bin/env python3
"""build_credit_spreads.py — IG + HY credit spreads (OAS).

Credit spreads (BAMLC0A0CM, BAMLH0A0HYM2 = HY) = early-cycle stress signal.
Widening spreads → HYG/JNK sell-off, energy HY blowup risk (APA, DVN, OXY),
regional banks (KRE).

Source: FRED ICE BofA indices.
Output: credit_spreads.csv
Columns: date, ig_oas_bps, hy_oas_bps, hy_yield_pct, ig_yield_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "credit_spreads.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("ig_oas_bps", "BAMLC0A0CM"),
    ("hy_oas_bps", "BAMLH0A0HYM2"),
    ("hy_yield_pct", "BAMLH0A0HYM2EY"),
    ("ig_yield_pct", "BAMLC0A0CMEY"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"credit {sid}: {e}")
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
    dates = sorted(
        set().union(*(data[a].keys() for a in data)),
        reverse=True,
    )[:90]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        ig_oas = data["ig_oas_bps"].get(d, 0)
        hy_oas = data["hy_oas_bps"].get(d, 0)
        rows.append({
            "date": d,
            "ig_oas_bps": f"{ig_oas * 100:.0f}" if ig_oas < 20 else f"{ig_oas:.0f}",
            "hy_oas_bps": f"{hy_oas * 100:.0f}" if hy_oas < 40 else f"{hy_oas:.0f}",
            "hy_yield_pct": f"{data['hy_yield_pct'].get(d, 0):.2f}",
            "ig_yield_pct": f"{data['ig_yield_pct'].get(d, 0):.2f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "ig_oas_bps", "hy_oas_bps",
                "hy_yield_pct", "ig_yield_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"credit_spreads: {len(rows)} days | latest {latest.get('date','?')} "
          f"hy_oas={latest.get('hy_oas_bps','?')}bp -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
