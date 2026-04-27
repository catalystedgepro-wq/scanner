#!/usr/bin/env python3
"""build_nrc_reactor_status.py — NRC daily nuclear reactor power status.

Each morning the NRC publishes power output as % for every licensed
commercial reactor. Outages (unplanned) → natgas demand surges, regional
power prices spike (NEE, DUK, SO, EXC, CEG, VST, TLN). Planned refuelings
also signal quarter cadence.

Source: nrc.gov/reading-rm/doc-collections/event-status/reactor-status/
  - Today: PowerStatus.txt (fixed-width text, space-delimited)

Output: nrc_reactor_status.csv
Columns: report_date, unit, power_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nrc_reactor_status.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/PowerStatus.txt"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"nrc: {e}")
        return ""


def main() -> None:
    txt = fetch()
    # Format (fixed-width): unit name ... power%
    # Header has "Report Date" & power columns
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    today = dt.date.today().isoformat()
    for line in txt.splitlines():
        line = line.rstrip()
        if not line or line.startswith("Power") or line.startswith("Report"):
            continue
        # Match trailing integer (0-100) as power; prefix = unit name
        m = re.match(r"^(.+?)\s+(\d{1,3})\s*$", line)
        if not m:
            continue
        unit = m.group(1).strip()
        try:
            pct = int(m.group(2))
        except Exception:
            continue
        if pct > 100:
            continue
        rows.append({
            "report_date": today,
            "unit": unit[:60],
            "power_pct": pct,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["report_date", "unit", "power_pct", "captured_at"])
        w.writeheader()
        w.writerows(rows)
    n_out = sum(1 for r in rows if r["power_pct"] < 50)
    print(f"nrc_reactor_status: {len(rows)} reactors | {n_out} below 50% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
