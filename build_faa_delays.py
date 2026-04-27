#!/usr/bin/env python3
"""build_faa_delays.py — FAA National Airspace System ground delay/closure.

FAA publishes real-time ground delay programs, departure/arrival
delays, and airport closures via a public XML feed. Multi-hour delays
at hub airports (ATL, ORD, DFW, LAX, JFK, LGA, EWR) directly compress
airline operating margins and drive earnings misses.

Signal:
- ORD/ATL/DFW ground-delay >60 min = airline earnings pressure same
  day (AAL, DAL, UAL, LUV)
- LGA/EWR/JFK >90 min = NY-metro aviation disruption (AAL/DAL
  northeast corridor)
- Multi-day airport closure at major hub = immediate -3% to -8% move
  in affected carrier
- Volume of concurrent ground-delay programs = system-wide weather
  regime (summer thunderstorm season, winter storm)

Drives:
- Major US airlines: AAL, DAL, UAL, LUV, ALK, JBLU, SAVE
- Airport services: SKWS, HLT, MAR, HST
- Travel-leisure: EXPE, BKNG, ABNB (delay impacts rebooking surge)
- Jet-fuel refiners: VLO, MPC (delay = fuel-burn reduction short-term)

Source: nasstatus.faa.gov/api/airport-status-information (public XML,
no key, updated every ~5 min).
Output: faa_delays.csv
Columns: event_type, airport, reason, metric, value, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "faa_delays.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://nasstatus.faa.gov/api/airport-status-information"


def _t(x) -> str:
    if x is None:
        return ""
    return (x.text or "").strip()


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"faa_delays: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"faa_delays: keeping existing {OUT_CSV.name}")
        return

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"faa_delays: parse error: {e}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    rows: list[dict] = []

    for dt_el in root.findall("Delay_type"):
        name = _t(dt_el.find("Name"))

        # Ground Delay Programs: avg + max minutes
        for gd in dt_el.findall(".//Ground_Delay"):
            rows.append({
                "event_type": "ground_delay",
                "airport": _t(gd.find("ARPT"))[:8],
                "reason": _t(gd.find("Reason"))[:80],
                "metric": "avg_delay",
                "value": _t(gd.find("Avg"))[:40],
                "captured_at": now,
            })
            rows.append({
                "event_type": "ground_delay",
                "airport": _t(gd.find("ARPT"))[:8],
                "reason": _t(gd.find("Reason"))[:80],
                "metric": "max_delay",
                "value": _t(gd.find("Max"))[:40],
                "captured_at": now,
            })

        # Arrival/Departure delays
        for d in dt_el.findall(".//Delay"):
            airport = _t(d.find("ARPT"))
            reason = _t(d.find("Reason"))
            for ad in d.findall("Arrival_Departure"):
                typ = (ad.get("Type") or "").lower()
                rows.append({
                    "event_type": f"{typ}_delay",
                    "airport": airport[:8],
                    "reason": reason[:80],
                    "metric": "min_delay",
                    "value": _t(ad.find("Min"))[:40],
                    "captured_at": now,
                })
                rows.append({
                    "event_type": f"{typ}_delay",
                    "airport": airport[:8],
                    "reason": reason[:80],
                    "metric": "max_delay",
                    "value": _t(ad.find("Max"))[:40],
                    "captured_at": now,
                })
                rows.append({
                    "event_type": f"{typ}_delay",
                    "airport": airport[:8],
                    "reason": reason[:80],
                    "metric": "trend",
                    "value": _t(ad.find("Trend"))[:40],
                    "captured_at": now,
                })

        # Airport closures
        for ac in dt_el.findall(".//Airport_Closure_List/Airport"):
            rows.append({
                "event_type": "closure",
                "airport": _t(ac.find("ARPT"))[:8],
                "reason": _t(ac.find("Reason"))[:80],
                "metric": "start",
                "value": _t(ac.find("Start"))[:40],
                "captured_at": now,
            })
            rows.append({
                "event_type": "closure",
                "airport": _t(ac.find("ARPT"))[:8],
                "reason": _t(ac.find("Reason"))[:80],
                "metric": "reopen",
                "value": _t(ac.find("Reopen"))[:40],
                "captured_at": now,
            })

    if not rows:
        # No delays ≠ empty fetch. Write a header + synthetic no-delay row.
        rows.append({
            "event_type": "clear",
            "airport": "ALL",
            "reason": "no active delays or closures",
            "metric": "status",
            "value": "clear",
            "captured_at": now,
        })

    fieldnames = ["event_type", "airport", "reason", "metric", "value",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    gd_count = sum(1 for r in rows
                   if r["event_type"] == "ground_delay"
                   and r["metric"] == "avg_delay")
    cl_count = sum(1 for r in rows
                   if r["event_type"] == "closure"
                   and r["metric"] == "start")
    arpts = sorted({r["airport"] for r in rows if r["airport"] != "ALL"})
    print(f"faa_delays: {len(rows)} rows | ground_delays={gd_count} "
          f"closures={cl_count} airports={len(arpts)} "
          f"({','.join(arpts[:6])}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
