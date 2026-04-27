#!/usr/bin/env python3
"""build_epa_tri.py — EPA Toxics Release Inventory by state.

US facility-level toxic-release reports. Regulatory/reputational risk
for industrial, chemical, refining, metals, and semi names:
- DOW, LYB, EMN, CE (chemicals)
- XOM, CVX, MPC, PSX (refining)
- NUE, STLD, X, CLF (steel)
- INTC, TXN (semi fab emissions)
- BA, LMT (aerospace metal plating)

Trade context:
- New TRI filing surge in state → sector-scoped ESG fund rebalance
- High-emission facility near election/ballot state → regulatory
  overhang risk premium
- Facility closure (fac_closed_ind=1) → asset-write-down narrative

Source: data.epa.gov/efservice/tri_facility (free, no key).
Output: epa_tri.csv
Columns: facility_id, name, state, city, zip, fips, closed,
         region, parent_co, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "epa_tri.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://data.epa.gov/efservice/tri_facility"

# Industrial-heavy states for equity-relevant emissions exposure.
STATES = ["CA", "TX", "LA", "PA", "OH", "IL", "IN", "MI", "NY", "NJ",
          "GA", "AL", "NC", "WV", "KY", "TN", "FL", "WA", "OR", "AZ"]


def _fetch(state: str, limit: int = 25) -> list:
    url = f"{BASE}/state_abbr/{state}/rows/0:{limit}/JSON"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        if isinstance(d, list):
            return d
        return []
    except Exception as e:
        print(f"epa_tri {state}: {e}")
        return []


def main() -> None:
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for state in STATES:
        facs = _fetch(state, limit=15)
        for f in facs:
            if not isinstance(f, dict):
                continue
            fid = (f.get("tri_facility_id") or "")[:20]
            if not fid or fid in seen_ids:
                continue
            seen_ids.add(fid)
            rows.append({
                "facility_id": fid,
                "name": (f.get("facility_name") or "")[:48],
                "state": state,
                "city": (f.get("city_name") or "")[:24],
                "zip": (f.get("zip_code") or "")[:10],
                "fips": (f.get("state_county_fips_code") or "")[:5],
                "closed": str(f.get("fac_closed_ind") or ""),
                "region": str(f.get("region") or ""),
                "parent_co": (f.get("mail_name") or "")[:32],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"epa_tri: no data, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["state"], r["name"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["facility_id", "name", "state", "city", "zip", "fips",
                  "closed", "region", "parent_co", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    closed = sum(1 for r in rows if r["closed"] == "1")
    per_state: dict[str, int] = {}
    for r in rows:
        per_state[r["state"]] = per_state.get(r["state"], 0) + 1
    print(f"epa_tri: {len(rows)} facilities ({len(per_state)} states) | "
          f"{closed} closed -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
