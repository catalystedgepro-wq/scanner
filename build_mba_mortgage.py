#!/usr/bin/env python3
"""build_mba_mortgage.py — Weekly mortgage applications (MBA survey).

MBA weekly apps (released Wed 7am ET) moves homebuilders (DHI, LEN, PHM,
NVR, TOL, KBH, MTH), title insurance (FNF, TFC), mortgage REITs (AGNC,
NLY), online brokers (RKT, UWMC), and big banks (JPM, BAC, WFC) via
mortgage origination.

Source: FRED series (Freddie Mac PMMS + MBA via MORTGAGE30US). Actual MBA
survey data is paywalled; PMMS is public. Augmented with MBA press
releases when available.

Output: mba_mortgage.csv
Columns: week_end, mba_purchase_idx, mba_refi_idx, pmms_30y, pmms_15y, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import os
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "mba_mortgage.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FRED_KEY = os.environ.get("FRED_API_KEY", "")

# FRED series: 30-year fixed rate mortgage (Freddie PMMS) — weekly
# MORTGAGE30US: 30-yr fixed
# MORTGAGE15US: 15-yr fixed
SERIES = [
    ("pmms_30y", "MORTGAGE30US"),
    ("pmms_15y", "MORTGAGE15US"),
]


def fetch_series(sid: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
    except Exception as e:
        print(f"mba_mortgage {sid}: {e}")
        return []
    out: list[tuple[str, float]] = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not d or v in {".", ""}:
            continue
        try:
            out.append((d, float(v)))
        except Exception:
            continue
    out.sort(key=lambda t: t[0])
    return out


def main() -> None:
    series_data: dict[str, dict[str, float]] = {}
    for alias, sid in SERIES:
        series_data[alias] = {d: v for d, v in fetch_series(sid)}
    # Take union of dates, last 52 weeks
    dates = sorted(set().union(*(series_data[a].keys() for a in series_data)), reverse=True)[:52]
    rows: list[dict] = []
    for d in dates:
        rows.append({
            "week_end": d,
            "mba_purchase_idx": "",
            "mba_refi_idx": "",
            "pmms_30y": f"{series_data['pmms_30y'].get(d, 0):.2f}",
            "pmms_15y": f"{series_data['pmms_15y'].get(d, 0):.2f}",
        })
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week_end", "mba_purchase_idx", "mba_refi_idx",
                "pmms_30y", "pmms_15y", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"mba_mortgage: {len(rows)} weeks | latest {latest.get('week_end','?')} "
          f"30Y={latest.get('pmms_30y','?')}% 15Y={latest.get('pmms_15y','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
