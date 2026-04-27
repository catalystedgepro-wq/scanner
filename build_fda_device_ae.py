#!/usr/bin/env python3
"""build_fda_device_ae.py — openFDA device adverse event aggregate.

Top device manufacturers by MDR adverse event count.
Signals material for medical-device names:
- Device recalls & Class I/II actions (ABT, MDT, BSX, SYK, ZBH, ISRG,
  DXCM, PODD, HOLX)
- Shareholder class actions following adverse-event clusters
- Market share rebalancing when a competitor has an AE spike

Source: openFDA /device/event.json.

Output: fda_device_ae.csv
Columns: manufacturer, ae_count_2y, rank, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fda_device_ae.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://api.fda.gov/device/event.json"


def main() -> None:
    today = dt.date.today()
    start = today - dt.timedelta(days=730)
    qs = urllib.parse.urlencode({
        "search": f"date_received:[{start.strftime('%Y%m%d')} TO "
                  f"{today.strftime('%Y%m%d')}]",
        "count": "device.manufacturer_d_name.exact",
        "limit": 100,
    })
    url = f"{BASE}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"fda_device_ae: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_device_ae: keeping existing {OUT_CSV.name}")
        return

    results = d.get("results") or []
    if not results:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fda_device_ae: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")

    rows: list[dict] = []
    for i, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue
        rows.append({
            "manufacturer": str(item.get("term") or "")[:80],
            "ae_count_2y": str(int(item.get("count") or 0)),
            "rank": str(i),
            "captured_at": now,
        })

    fieldnames = ["manufacturer", "ae_count_2y", "rank", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top = rows[0] if rows else {}
    print(f"fda_device_ae: {len(rows)} manufacturers (2-y MDR) | "
          f"top: {top.get('manufacturer', '?')}="
          f"{top.get('ae_count_2y', '?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
