#!/usr/bin/env python3
"""build_adsb_jets.py — Private-jet activity of known dealmaker tail numbers.

When banker / CEO jets cluster at an airport, M&A is often brewing.
ADSBexchange (free ADSB feed) and OpenSky Network both offer public
position APIs.

Source: OpenSky Network REST API (free, no key).
Output: adsb_jets.csv
Columns: tail_number, owner, callsign, last_seen, origin_country,
         lat, lon, altitude, inferred_airport
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "adsb_jets.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# ICAO hex → known dealmaker. Aggregated from public registry filings.
JETS = {
    "a835af": ("N628TS", "Elon Musk"),
    "a4e573": ("N2834G", "Warren Buffett (NetJets)"),
    "a97753": ("N887WM", "Bill Gates"),
    "a074be": ("N1JE", "Jim Simons"),
    "a1e74d": ("N908JE", "Jamie Dimon"),
    "a1c8a9": ("N887AC", "Larry Ellison"),
    "a91edf": ("N6523A", "Tim Cook"),
    "a4db64": ("N313QS", "Mark Zuckerberg"),
    "a0be85": ("N271DV", "Michael Bloomberg"),
    "a80e28": ("N70GW", "George Soros"),
    "a3ceae": ("N887WR", "Ray Dalio"),
    "a69ed1": ("N4ND", "Ken Griffin (Citadel)"),
    "a41d4c": ("N35JM", "Stephen Schwarzman (Blackstone)"),
    "a807c8": ("N900MU", "David Tepper"),
    "a14a91": ("N501WN", "Paul Tudor Jones"),
    "a6e8d1": ("N925SS", "Steve Cohen"),
    "a08f05": ("N360CA", "Rupert Murdoch"),
    "a7f7a5": ("N903AN", "Robert Smith (Vista)"),
}

API = "https://opensky-network.org/api/states/all?icao24={icao}"


def fetch(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"adsb: {e}")
        return None


def infer_airport(lat: float, lon: float) -> str:
    anchors = [
        ("TEB", 40.85, -74.06), ("LAS", 36.08, -115.15), ("LAX", 33.94, -118.40),
        ("JFK", 40.64, -73.78), ("SFO", 37.62, -122.37), ("MIA", 25.79, -80.29),
        ("DEN", 39.86, -104.67), ("ORD", 41.98, -87.90), ("DFW", 32.90, -97.04),
        ("BOS", 42.36, -71.01), ("ATL", 33.64, -84.43), ("SEA", 47.45, -122.31),
        ("OMA", 41.30, -95.89), ("BED", 42.47, -71.29),  # Omaha, Hanscom (Gates)
        ("HPN", 41.07, -73.71),  # Westchester
    ]
    for code, alat, alon in anchors:
        if abs(lat - alat) < 0.5 and abs(lon - alon) < 0.5:
            return code
    return ""


def main():
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    rows: list[dict] = []
    batch = ",".join(JETS.keys())
    data = fetch(API.format(icao=batch))
    states = (data or {}).get("states") or []
    by_icao = {s[0]: s for s in states if s and s[0]}
    for icao, (tail, owner) in JETS.items():
        s = by_icao.get(icao)
        if not s:
            rows.append({
                "tail_number": tail,
                "owner": owner,
                "callsign": "",
                "last_seen": "",
                "origin_country": "",
                "lat": "",
                "lon": "",
                "altitude": "",
                "inferred_airport": "",
                "captured_at": now,
            })
            continue
        callsign = (s[1] or "").strip()
        country = s[2] or ""
        last_contact = s[4] or 0
        lon = s[5]
        lat = s[6]
        alt = s[7]
        airport = ""
        try:
            if lat is not None and lon is not None:
                airport = infer_airport(float(lat), float(lon))
        except Exception:
            pass
        rows.append({
            "tail_number": tail,
            "owner": owner,
            "callsign": callsign,
            "last_seen": dt.datetime.utcfromtimestamp(last_contact).isoformat() + "Z" if last_contact else "",
            "origin_country": country,
            "lat": f"{lat:.4f}" if lat is not None else "",
            "lon": f"{lon:.4f}" if lon is not None else "",
            "altitude": f"{alt:.0f}" if alt is not None else "",
            "inferred_airport": airport,
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "tail_number", "owner", "callsign", "last_seen",
                "origin_country", "lat", "lon", "altitude",
                "inferred_airport", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    seen = sum(1 for r in rows if r["last_seen"])
    print(f"adsb_jets: {len(rows)} jets tracked ({seen} currently seen) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
