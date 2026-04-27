#!/usr/bin/env python3
"""build_usda_crop_progress.py — Weekly USDA crop progress + condition.

Monday 4pm ET report drives corn (ZC, CORN), soy (ZS, SOYB), wheat (ZW,
WEAT), cotton (CT) futures and downstream: ADM, BG, MOS, NTR, CF, CTVA,
DE (equipment), TSN (chicken feed), HRL, PPC.

Source: USDA NASS Quick Stats API (free, no key for basic queries;
USDA_NASS_API_KEY for higher rate limits).

Output: usda_crop_progress.csv
Columns: date, crop, metric, state, value, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usda_crop_progress.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = os.environ.get("USDA_NASS_API_KEY", "")

CROPS = ["CORN", "SOYBEANS", "WHEAT", "COTTON"]
CURRENT_YEAR = dt.date.today().year


def fetch(crop: str) -> list:
    if not KEY:
        # Without a key, NASS still responds but rate-limited; provide stub
        return []
    url = (
        "https://quickstats.nass.usda.gov/api/api_GET/"
        f"?key={KEY}&commodity_desc={crop}"
        "&statisticcat_desc=PROGRESS&agg_level_desc=NATIONAL"
        f"&year={CURRENT_YEAR}&format=JSON"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8"))
            return d.get("data") or []
    except Exception as e:
        print(f"usda_crop {crop}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for crop in CROPS:
        data = fetch(crop)
        for rec in data:
            rows.append({
                "date": rec.get("week_ending") or rec.get("load_time") or "",
                "crop": crop,
                "metric": rec.get("short_desc", "")[:100],
                "state": rec.get("state_name") or "US",
                "value": rec.get("Value") or rec.get("value") or "",
                "captured_at": now,
            })
    rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    rows = rows[:200]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "crop", "metric", "state", "value", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"usda_crop_progress: {len(rows)} obs "
          f"({'KEYED' if KEY else 'NO-KEY stub'}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
