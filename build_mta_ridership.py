#!/usr/bin/env python3
"""build_mta_ridership.py — NYC/MTA daily ridership & traffic.

MTA daily ridership is the cleanest high-frequency consumer-activity
signal available from a free public feed. Subway + bus + LIRR + MNR +
Access-A-Ride + bridges/tunnels tolls. Covers ~30% of US daily transit
trips and correlates with NYC-centric earnings (office REITs SLG/VNO,
quick-service NYC-heavy like SHAK/CMG, transit ad CMG-D, outdoor media
OUT, ride-share UBER/LYFT substitution, retail FL/GPS/M), and broadly
with the US "return-to-office" / urban mobility narrative.

Causal chain: ridership rebound -> SLG/VNO cover rallies, SBUX/SHAK
urban same-store lift, outdoor ad (OUT, LAMR) beats. Ridership drop
during winter storms -> DPZ/PZZA delivery volume spike, FDX/UPS last-
mile acceleration.

Source: data.ny.gov Socrata dataset `sayj-mze2` (MTA Daily Ridership
and Traffic: Beginning 2020). Long format (date, mode, count). Updates
~24h lag. Public, no auth, rate-limit forgiving.

Output: mta_ridership.csv
Columns: date, subways, buses, lirr, mnr, access_a_ride, bridges_tunnels,
         staten_island, total_riders, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "mta_ridership.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Socrata CSV endpoint — 12 most recent weeks of daily rows.
BASE = "https://data.ny.gov/resource/sayj-mze2.csv"

# Mode codes used by the dataset.
MODE_MAP = {
    "Subway": "subways",
    "Bus": "buses",
    "LIRR": "lirr",
    "MNR": "mnr",
    "AAR": "access_a_ride",
    "BT": "bridges_tunnels",
    "SIR": "staten_island",
    # NYC congestion-pricing entries (post-Jan 2025). Strong proxy for
    # Manhattan office re-occupancy / retail foot traffic.
    "CRZ Entries": "crz_entries",
    "CBD Entries": "cbd_entries",
}

# Ridership modes only (exclude tolls/cordon counts) -> transit total.
RIDER_MODES = {"subways", "buses", "lirr", "mnr", "access_a_ride",
               "staten_island"}


def fetch() -> str | None:
    # Pull latest 90 days across all modes (7 modes × 90 days = 630 rows).
    cutoff = (dt.date.today() - dt.timedelta(days=95)).isoformat()
    params = {
        "$where": f"date >= '{cutoff}'",
        "$order": "date DESC",
        "$limit": "1200",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"mta_ridership: {e}")
        return None


def main() -> None:
    body = fetch() or ""
    per_day: dict[str, dict[str, int]] = defaultdict(dict)
    if body.strip() and not body.lstrip().startswith("<"):
        reader = csv.reader(body.splitlines())
        header = next(reader, None) or []
        try:
            d_i = header.index("date")
            m_i = header.index("mode")
            c_i = header.index("count")
        except ValueError:
            d_i, m_i, c_i = 0, 1, 2
        for cells in reader:
            if len(cells) <= c_i:
                continue
            date = cells[d_i][:10]  # strip time
            mode = cells[m_i].strip()
            key = MODE_MAP.get(mode)
            if not key:
                continue
            try:
                per_day[date][key] = int(float(cells[c_i]))
            except ValueError:
                continue
    if not per_day and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"mta_ridership: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    rows: list[dict] = []
    for date in sorted(per_day.keys()):
        d = per_day[date]
        total = sum(d.get(k, 0) for k in RIDER_MODES)
        rows.append({
            "date": date,
            "subways": d.get("subways", ""),
            "buses": d.get("buses", ""),
            "lirr": d.get("lirr", ""),
            "mnr": d.get("mnr", ""),
            "access_a_ride": d.get("access_a_ride", ""),
            "bridges_tunnels": d.get("bridges_tunnels", ""),
            "staten_island": d.get("staten_island", ""),
            "crz_entries": d.get("crz_entries", ""),
            "cbd_entries": d.get("cbd_entries", ""),
            "total_riders": total,
        })
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "subways", "buses", "lirr", "mnr",
                        "access_a_ride", "bridges_tunnels",
                        "staten_island", "crz_entries", "cbd_entries",
                        "total_riders", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"mta_ridership: {len(rows)} days | latest "
          f"{latest.get('date','?')} subway="
          f"{latest.get('subways','?')} total="
          f"{latest.get('total_riders','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
