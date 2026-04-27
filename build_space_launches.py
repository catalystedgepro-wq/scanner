#!/usr/bin/env python3
"""build_space_launches.py — Upcoming rocket launches worldwide.

TheSpaceDevs Launch Library v2 aggregates all announced launches from
all providers (SpaceX, ULA, Rocket Lab, Blue Origin, ArianeSpace, CNSA,
ISRO, Roscosmos, etc.). Free, rate-limited API (~15 req/hr).

Event tape relevant to space sector:
- RKLB (Rocket Lab) launches every 2-3 weeks; each success = tape
- ASTS (AST SpaceMobile) constellation deployments — SpaceX Starlink
  comp trigger, moves ASTS ±8% same day
- ULA Vulcan milestones → LMT/BA JV, pricing for NROL contracts
- Blue Origin New Glenn → $AMZN space spend narrative
- ISRO (ILS), SpaceX Starship → defense contract positioning (LMT,
  NOC, RTX)

Output: space_launches.csv
Columns: launch_id, name, date_utc, status, rocket, provider,
pad, mission, window_start, captured_at

Source: ll.thespacedevs.com/2.2.0/launch/upcoming (no key, live).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "space_launches.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=40"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"space_launches: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"space_launches: keeping existing {OUT_CSV.name}")
        return

    results = d.get("results") or []
    rows: list[dict] = []
    for r in results:
        status = (r.get("status") or {}).get("abbrev", "")
        rocket = ((r.get("rocket") or {}).get("configuration") or {})
        rocket_name = rocket.get("name", "") or rocket.get("full_name", "")
        launch_provider = ((r.get("launch_service_provider") or {}).get("name",
                                                                        ""))
        pad_obj = r.get("pad") or {}
        pad = pad_obj.get("name", "")
        loc = (pad_obj.get("location") or {}).get("name", "")
        mission = (r.get("mission") or {}).get("name", "")
        rows.append({
            "launch_id": (r.get("id") or "")[:36],
            "name": (r.get("name") or "")[:64],
            "date_utc": (r.get("net") or "")[:20],
            "window_start": (r.get("window_start") or "")[:20],
            "status": status[:12],
            "rocket": rocket_name[:32],
            "provider": launch_provider[:32],
            "pad": pad[:32],
            "location": loc[:32],
            "mission": mission[:48],
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"space_launches: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["date_utc"])

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["launch_id", "name", "date_utc", "window_start",
                  "status", "rocket", "provider", "pad", "location",
                  "mission", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    next_up = rows[0] if rows else {}
    spacex = sum(1 for r in rows if "SpaceX" in r["provider"])
    rklb = sum(1 for r in rows if "Rocket Lab" in r["provider"])
    print(f"space_launches: {len(rows)} upcoming | next: "
          f"{next_up.get('name','?')} @ {next_up.get('date_utc','?')[:10]} "
          f"({next_up.get('provider','?')}) | SpaceX={spacex} "
          f"RocketLab={rklb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
