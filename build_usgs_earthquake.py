#!/usr/bin/env python3
"""build_usgs_earthquake.py — Global M5.5+ earthquakes (last 30 days).

Major quakes hit TSM/foundries (Taiwan), ASML supply chain (Japan/Korea),
reinsurance (RE, RNR, EG), construction (SUM, MLM, VMC). M6+ in the
"Ring of Fire" is an auto-flag — historical moves 3–15% in semis.

Source: USGS comcat feed (free JSON, no key).
Output: usgs_earthquake.csv
Columns: event_id, time_utc, magnitude, location, lat, lon, depth_km,
         region_tag, tickers_affected, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usgs_earthquake.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# 30-day feed, magnitude ≥ 4.5 (we filter to 5.5+ for signal)
FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson"

# Region → tickers known to be exposed (semis, insurers, construction)
REGION_TICKERS = {
    "taiwan":    "TSM,UMC,HIMX,ASX,SIMO,ASML",
    "japan":     "TM,HMC,SONY,NTDOY,MUFG,SMFG",
    "korea":     "KB,SHG,LPL,KEP,DL,KNYJY",
    "chile":     "SQM,BHP,RIO,FCX",
    "peru":      "SCCO,FCX",
    "mexico":    "GMK,SPGI,VISTA,CX",
    "indonesia": "ICCH,TLK,GRAB",
    "turkey":    "TKC,ANSGR,KOC",
    "california":"DIS,GOOG,AAPL,META,NFLX",
    "alaska":    "XOM,HES,BP",
    "philippines":"PLDT,NILE",
    "puerto_rico":"BDPRA,FBP",
}


def tag_region(place: str, lat: float, lon: float) -> str:
    p = place.lower()
    if "taiwan" in p: return "taiwan"
    if "japan" in p: return "japan"
    if "korea" in p: return "korea"
    if "chile" in p: return "chile"
    if "peru" in p: return "peru"
    if "mexico" in p: return "mexico"
    if "indonesia" in p or "sumatra" in p or "java" in p: return "indonesia"
    if "turkey" in p: return "turkey"
    if "california" in p: return "california"
    if "alaska" in p: return "alaska"
    if "philippines" in p: return "philippines"
    if "puerto rico" in p: return "puerto_rico"
    return "other"


def fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"usgs_eq: {e}")
        return None


def main() -> None:
    data = fetch(FEED) or {}
    features = data.get("features") or []
    rows: list[dict] = []
    for f in features:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or [0, 0, 0]
        mag = props.get("mag")
        if mag is None or mag < 5.5:
            continue
        place = props.get("place") or ""
        t_ms = props.get("time") or 0
        try:
            t_iso = dt.datetime.utcfromtimestamp(t_ms / 1000).isoformat(timespec="seconds") + "Z"
        except Exception:
            t_iso = ""
        lon, lat, depth = (coords + [0, 0, 0])[:3]
        region = tag_region(place, lat, lon)
        rows.append({
            "event_id": f.get("id", ""),
            "time_utc": t_iso,
            "magnitude": f"{mag:.1f}",
            "location": place,
            "lat": f"{lat:.3f}",
            "lon": f"{lon:.3f}",
            "depth_km": f"{depth:.1f}",
            "region_tag": region,
            "tickers_affected": REGION_TICKERS.get(region, ""),
            "url": props.get("url", ""),
        })
    rows.sort(key=lambda r: r["time_utc"], reverse=True)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "event_id", "time_utc", "magnitude", "location",
                "lat", "lon", "depth_km", "region_tag",
                "tickers_affected", "url", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"usgs_earthquake: {len(rows)} M5.5+ events | latest "
          f"M{latest.get('magnitude','?')} {latest.get('region_tag','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
