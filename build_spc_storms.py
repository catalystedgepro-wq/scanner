#!/usr/bin/env python3
"""build_spc_storms.py — NOAA/SPC severe storm reports, daily.

Storm Prediction Center publishes a daily CSV bundle of tornado,
hail, and wind reports. Each report is geocoded with state/county,
time, magnitude, and narrative. Provides real-time catastrophe
tracking before NOAA Storm Events official dataset updates (months
lag).

Signal:
- Tornado clusters in insured-heavy states (TX, FL, OK, KS, MO) =
  CAT-event probability rising → short insurers, long reinsurance
  tail hedges
- Wind > 80 mph clusters = utility grid risk (DUK, SO, NEE, EIX,
  PCG outages)
- Hail > 2" clusters = auto insurer severity shock (PGR, ALL,
  TRV auto lines)

Drives:
- P&C insurers (ALL, PGR, TRV, CB, HIG, AIG, WRB, RLI, RNR)
- Reinsurance / ILS (RNR, EG, AXS, ARE)
- Utilities (NEE, DUK, SO, EIX, XEL, D, AEP)
- Homebuilders (DHI, LEN, PHM — rebuild bid)
- Home improvement surge buyers (HD, LOW — post-event)
- Disaster restoration (BCO, BELFOR-adjacent small caps)

Source: spc.noaa.gov/climo/reports/{YYMMDD}_rpts.csv (+ today.csv).
Output: spc_storms.csv
Columns: report_date, event_type, time_utc, magnitude, state,
         county, location, lat, lon, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "spc_storms.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
DAYS_BACK = 7


def _fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"spc_storms: {url}: {e}")
        return None


def _parse_section(date_iso: str, text: str) -> list[dict]:
    """SPC CSV has 3 concatenated sections: Tornado, Wind, Hail.

    Each section starts with a repeat of the header. We track which
    section by counting header occurrences.
    """
    out: list[dict] = []
    section_order = ["tornado", "wind", "hail"]
    section_idx = -1
    reader = csv.reader(StringIO(text))
    for row in reader:
        if not row:
            continue
        if row and row[0] == "Time":
            section_idx += 1
            continue
        if len(row) < 8:
            continue
        if section_idx < 0 or section_idx >= len(section_order):
            continue
        event = section_order[section_idx]
        try:
            out.append({
                "report_date": date_iso,
                "event_type": event,
                "time_utc": row[0],
                "magnitude": row[1],
                "location": row[2][:60],
                "county": row[3][:30],
                "state": row[4][:3],
                "lat": row[5],
                "lon": row[6],
            })
        except Exception:
            continue
    return out


def main() -> None:
    rows: list[dict] = []
    today = dt.datetime.now(dt.timezone.utc).date()

    for offset in range(DAYS_BACK + 1):
        d = today - dt.timedelta(days=offset)
        # SPC uses YYMMDD.
        short = d.strftime("%y%m%d")
        url = f"https://www.spc.noaa.gov/climo/reports/{short}_rpts.csv"
        text = _fetch(url)
        if not text:
            continue
        rows.extend(_parse_section(d.isoformat(), text))

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"spc_storms: empty, keeping existing {OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["report_date", "event_type", "time_utc", "magnitude",
                  "state", "county", "location", "lat", "lon",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary counts.
    counts: dict[str, int] = {"tornado": 0, "wind": 0, "hail": 0}
    states: dict[str, int] = {}
    for r in rows:
        counts[r["event_type"]] = counts.get(r["event_type"], 0) + 1
        s = r["state"]
        states[s] = states.get(s, 0) + 1
    top_states = sorted(states.items(), key=lambda kv: kv[1],
                        reverse=True)[:4]
    bits = [f"{k}={v}" for k, v in counts.items()]
    bits.append(f"top_states=" + ",".join(f"{s}={n}" for s, n in top_states))
    print(f"spc_storms: {len(rows)} reports | last {DAYS_BACK+1}d | "
          f"{' '.join(bits)} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
