#!/usr/bin/env python3
"""build_noaa_weather_alerts.py — NWS active weather alerts (US).

Severe weather alerts (tornado, severe thunderstorm, flood, winter
storm, excessive heat) affect: utilities (demand surge → NRG, VST,
XEL), airlines (cancellations → DAL, AAL, UAL, LUV ticker drops),
insurance (claims → TRV, PGR, ALL), rail (UNP, CSX, NSC, CP delays),
agriculture (ADM, BG, CF, MOS, NTR), retail (storm prep → HD, LOW,
TSCO, WMT, COST).

Source: api.weather.gov/alerts/active (free, no key, JSON).
Output: noaa_weather_alerts.csv
Columns: alert_id, event, severity, urgency, areas, sent, expires,
         headline, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "noaa_weather_alerts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = "https://api.weather.gov/alerts/active"


def fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"nws: {e}")
        return []
    return data.get("features", []) or []


def main() -> None:
    feats = fetch()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    SEVERITY_ORDER = {
        "Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1, "Unknown": 0,
    }
    for f in feats:
        p = f.get("properties", {}) or {}
        rows.append({
            "alert_id": p.get("id", "")[:80],
            "event": p.get("event", ""),
            "severity": p.get("severity", ""),
            "urgency": p.get("urgency", ""),
            "areas": (p.get("areaDesc") or "")[:200],
            "sent": p.get("sent", ""),
            "expires": p.get("expires", ""),
            "headline": (p.get("headline") or "")[:160],
            "captured_at": now,
        })
    rows.sort(
        key=lambda r: SEVERITY_ORDER.get(r.get("severity") or "", 0),
        reverse=True,
    )
    rows = rows[:300]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "alert_id", "event", "severity", "urgency",
                "areas", "sent", "expires", "headline", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"nws_alerts: {len(rows)} active | top "
          f"{top.get('severity','?')}/{top.get('event','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
