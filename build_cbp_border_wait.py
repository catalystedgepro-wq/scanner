#!/usr/bin/env python3
"""build_cbp_border_wait.py — CBP border crossing wait times.

US-Canada and US-Mexico border crossing delays are a direct
trade-flow signal. Commercial-vehicle lane delays at major ports
(Laredo, Otay Mesa, El Paso, Detroit, Buffalo-Niagara) telegraph:
- Auto/electronics inventory friction → GM/F/STLA/TSLA, AAPL
- Fresh produce price pressure → COST/WMT margin, KR, SYY
- Cross-border e-commerce delays → SHOP, PDD/TEMU
- Spillover rail/trucking volume signals → CSX, KSU, CNI, CP, KNX

Closures or hour-long+ delays at the top-10 commercial ports
(Laredo Bridge II is #1 by value, ~$220B/yr) are specifically
event-risk catalysts.

Output: cbp_border_wait.csv
Columns: port_number, port_name, crossing_name, border, port_status,
cv_delay_min, cv_lanes_open, pv_delay_min, pv_lanes_open,
pedestrian_delay_min, captured_at

Source: bwt.cbp.gov/api/bwtnew (no key, live, refreshes every 15m).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cbp_border_wait.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://bwt.cbp.gov/api/bwtnew"


def _leg(lane_block: dict, key: str) -> tuple[str, str]:
    """Return (delay_minutes, lanes_open) for a lane subsection."""
    sub = (lane_block or {}).get(key) or {}
    return (
        str(sub.get("delay_minutes") or "").strip(),
        str(sub.get("lanes_open") or "").strip(),
    )


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"cbp_border_wait: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cbp_border_wait: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(d, list) or not d:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cbp_border_wait: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows: list[dict] = []
    for e in d:
        cv_delay, cv_lanes = _leg(
            e.get("commercial_vehicle_lanes") or {}, "standard_lanes")
        pv_delay, pv_lanes = _leg(
            e.get("passenger_vehicle_lanes") or {}, "standard_lanes")
        ped_delay, _ = _leg(
            e.get("pedestrian_lanes") or {}, "standard_lanes")
        rows.append({
            "port_number": (e.get("port_number") or "")[:10],
            "port_name": (e.get("port_name") or "")[:40],
            "crossing_name": (e.get("crossing_name") or "")[:60],
            "border": (e.get("border") or "")[:30],
            "port_status": (e.get("port_status") or "")[:12],
            "hours": (e.get("hours") or "")[:30],
            "cv_delay_min": cv_delay,
            "cv_lanes_open": cv_lanes,
            "pv_delay_min": pv_delay,
            "pv_lanes_open": pv_lanes,
            "pedestrian_delay_min": ped_delay,
            "report_date": f"{e.get('date','')} {e.get('time','')}",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cbp_border_wait: no rows, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Sort by commercial-vehicle delay desc (trade signal).
    def cv(r: dict) -> float:
        try:
            return -float(r["cv_delay_min"] or "0")
        except ValueError:
            return 0.0

    rows.sort(key=cv)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["border", "port_number", "port_name", "crossing_name",
                  "port_status", "hours",
                  "cv_delay_min", "cv_lanes_open",
                  "pv_delay_min", "pv_lanes_open",
                  "pedestrian_delay_min",
                  "report_date", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    closed = sum(1 for r in rows if r["port_status"].lower() != "open")
    heavy = [r for r in rows if r["cv_delay_min"] and
             r["cv_delay_min"].isdigit() and int(r["cv_delay_min"]) >= 60]
    worst = rows[0] if rows else None
    wbit = (f"worst CV: {worst['port_name']} "
            f"{worst['cv_delay_min']}min" if worst else "")
    print(f"cbp_border_wait: {len(rows)} ports "
          f"({closed} closed, {len(heavy)} CV>=60min) | {wbit} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
