#!/usr/bin/env python3
"""build_fx_rates.py — Major FX pairs (daily).

USD strength (DXY) = direct drag on S&P earnings (40% international).
Strong DXY hurts AAPL, MSFT, KO, PG, CAT, ORCL non-US revenue.
USDJPY dislocation = BOJ intervention signal. USDCNY = trade-war
proxy (FXI, YINN).

Source: FRED DTWEXBGS (broad), DEXJPUS, DEXCHUS, DEXUSEU, DEXUSUK.
Output: fx_rates.csv
Columns: date, dxy_broad, usdjpy, usdcny, eurusd, gbpusd, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fx_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("dxy", "DTWEXBGS"),
    ("usdjpy", "DEXJPUS"),
    ("usdcny", "DEXCHUS"),
    ("eurusd", "DEXUSEU"),
    ("gbpusd", "DEXUSUK"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"fx {sid}: {e}")
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
    return out[-180:]


def main() -> None:
    data = {a: dict(fetch(s)) for a, s in SERIES}
    all_dates: set[str] = set()
    for d in data.values():
        all_dates |= d.keys()
    dates = sorted(all_dates, reverse=True)[:120]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        rows.append({
            "date": d,
            "dxy_broad": f"{data['dxy'].get(d, 0):.3f}",
            "usdjpy": f"{data['usdjpy'].get(d, 0):.2f}",
            "usdcny": f"{data['usdcny'].get(d, 0):.4f}",
            "eurusd": f"{data['eurusd'].get(d, 0):.4f}",
            "gbpusd": f"{data['gbpusd'].get(d, 0):.4f}",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "dxy_broad", "usdjpy", "usdcny",
                "eurusd", "gbpusd", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"fx: {len(rows)} days | latest {latest.get('date','?')} "
          f"dxy={latest.get('dxy_broad','?')} usdjpy={latest.get('usdjpy','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
