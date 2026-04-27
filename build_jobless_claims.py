#!/usr/bin/env python3
"""build_jobless_claims.py — Initial + continuing claims (weekly).

Claims lead NFP by 2-4 weeks. Spike above 300k = recession trigger,
XLY crushed, defensive rotation (XLP, XLV, XLU). Falling claims =
labor tight, Fed hawkish, small caps (IWM) choked. Released every
Thursday 8:30a ET.

Source: FRED ICSA (initial), CCSA (continuing), IC4WSA (4-wk avg).
Output: jobless_claims.csv
Columns: week, initial, continuing, initial_4wma, initial_wow, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "jobless_claims.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = [
    ("initial", "ICSA"),
    ("continuing", "CCSA"),
    ("initial_4wma", "IC4WSA"),
]


def fetch(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"claims {sid}: {e}")
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
    sorted_dates = sorted(data["initial"].keys())
    idx = {d: i for i, d in enumerate(sorted_dates)}
    dates = sorted(data["initial"].keys(), reverse=True)[:104]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for d in dates:
        cur = data["initial"].get(d, 0)
        i = idx.get(d, -1)
        prev = data["initial"].get(sorted_dates[i - 1], 0) if i >= 1 else 0
        rows.append({
            "week": d,
            "initial": f"{cur:.0f}",
            "continuing": f"{data['continuing'].get(d, 0):.0f}",
            "initial_4wma": f"{data['initial_4wma'].get(d, 0):.0f}",
            "initial_wow": f"{(cur - prev):+.0f}" if prev else "",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week", "initial", "continuing",
                "initial_4wma", "initial_wow", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"claims: {len(rows)} weeks | latest {latest.get('week','?')} "
          f"ic={latest.get('initial','?')}k cc={latest.get('continuing','?')}k "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
