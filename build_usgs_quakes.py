#!/usr/bin/env python3
"""build_usgs_quakes.py — USGS significant earthquakes (past 30 days).

Major seismic events drive three equity complexes:
- **Reinsurance** (RE, RNR, EG, MHO): M7+ in high-exposure regions
  (Japan, CA, Turkey) triggers 2-5% drawdown on expected loss.
- **Nuclear / utilities**: M6+ near nuclear facility = multi-day outage
  risk for the operator; watch JPXN, EDF, NEE near West Coast plants.
- **Japan complex** (EWJ, ITOCY, TM, HMC, SONY, 7203.T ADR): M6.5+ in
  Japan historically drops EWJ 1-3% and extends for 3-5 sessions.
- **Semi supply chain**: M6+ in Taiwan = TSM supply disruption risk,
  10-15% price shock possible on prolonged downtime.

Trade uses:
- M7.0+ anywhere: global reinsurance rate-hike narrative, long RE/RNR
  over 30-day horizon.
- M6.5+ Japan/Taiwan: short EWJ/TSM on news, cover in 3-5 sessions.
- M5+ cluster (>5 events in 24h same region): volcanic/precursor signal,
  follow-up quake risk elevated.

Source: earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson
(free, no key, GeoJSON, updated ~5 min).

Output: usgs_quakes.csv
Columns: time, mag, place, lat, lon, depth_km, tsunami, alert,
         significance, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usgs_quakes.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson"


def fetch() -> dict | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"usgs_quakes: {e}")
        return None


def main() -> None:
    data = fetch() or {}
    features = data.get("features") or []
    if not features and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"usgs_quakes: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows: list[dict] = []
    for f in features:
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        t_ms = props.get("time")
        try:
            t_iso = dt.datetime.fromtimestamp(
                int(t_ms) / 1000, tz=dt.timezone.utc,
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (ValueError, TypeError):
            t_iso = ""
        rows.append({
            "time": t_iso,
            "mag": props.get("mag", ""),
            "place": (props.get("place") or "")[:100],
            "lat": coords[1] if len(coords) > 1 else "",
            "lon": coords[0] if len(coords) > 0 else "",
            "depth_km": coords[2] if len(coords) > 2 else "",
            "tsunami": props.get("tsunami", 0),
            "alert": props.get("alert") or "",
            "significance": props.get("sig", ""),
            "url": props.get("url", ""),
        })

    rows.sort(key=lambda r: r["time"], reverse=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["time", "mag", "place", "lat", "lon", "depth_km",
                        "tsunami", "alert", "significance", "url",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    big = [r for r in rows if isinstance(r["mag"], (int, float)) and r["mag"] >= 6.0]
    latest = rows[0] if rows else {}
    print(f"usgs_quakes: {len(rows)} M4.5+ (30d) | {len(big)} M6.0+ | "
          f"latest {latest.get('time','?')} M{latest.get('mag','?')} "
          f"{latest.get('place','?')[:40]} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
