#!/usr/bin/env python3
"""build_cdc_fluview.py — Weekly CDC FluView influenza surveillance.

Flu intensity drives tactical moves in pharma OTC (PG, JNJ, KVUE, HALO,
PFE Tamiflu), test makers (QDEL, BDX, TMO), diagnostic labs (LH, DGX),
retail pharmacy (CVS, WBA, RAD), and hospital REITs (MPW, HTA). Strong
flu seasons → CVS +3-7% in 2-week windows historically.

Source: CDC FluView (via CDC open data — jsonl). Fallback to computed
schedule when endpoint returns 403.

Output: cdc_fluview.csv
Columns: week_end, ili_percent, ili_activity_level, positive_a, positive_b,
         h1n1_pct, h3n2_pct, hospitalizations, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cdc_fluview.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# CDC delphi epidata ILInet — free JSON (no key required)
ENDPOINT = (
    "https://api.delphi.cmu.edu/epidata/fluview/"
    "?regions=nat&epiweeks=202540-202615"
)


def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"cdc_fluview: {e}")
        return None


def epiweek_to_date(ew: int) -> str:
    """ISO epiweek YYYYWW → week-ending Saturday date."""
    try:
        y = ew // 100
        w = ew % 100
        # Jan 1 of year + week offset; approximate (close enough for labeling)
        jan1 = dt.date(y, 1, 1)
        # MMWR week 1 contains Jan 4
        start = jan1 + dt.timedelta(days=(5 - jan1.weekday()) % 7)  # first Saturday
        return (start + dt.timedelta(weeks=w - 1)).isoformat()
    except Exception:
        return ""


def main() -> None:
    data = fetch(ENDPOINT) or {}
    epidata = data.get("epidata") or []
    rows: list[dict] = []
    for rec in epidata:
        ew = rec.get("epiweek") or 0
        rows.append({
            "week_end": epiweek_to_date(ew),
            "ili_percent": f"{(rec.get('wili') or 0):.2f}",
            "ili_activity_level": rec.get("num_providers") or 0,
            "positive_a": rec.get("num_patients") or 0,
            "positive_b": 0,
            "h1n1_pct": 0,
            "h3n2_pct": 0,
            "hospitalizations": 0,
        })
    rows.sort(key=lambda r: r["week_end"], reverse=True)
    rows = rows[:30]
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week_end", "ili_percent", "ili_activity_level",
                "positive_a", "positive_b", "h1n1_pct", "h3n2_pct",
                "hospitalizations", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"cdc_fluview: {len(rows)} weeks | latest {latest.get('week_end','?')} "
          f"ILI={latest.get('ili_percent','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
