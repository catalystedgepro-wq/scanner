#!/usr/bin/env python3
"""build_nws_alerts.py — NWS severe-weather alert snapshot.

National Weather Service publishes active advisories, watches and
warnings nationwide. Severe/extreme alerts map directly to trading
signals:

- Hurricanes, tornado outbreaks, ice storms -> insurer loss ratio
  repricing (ALL/TRV/PGR/CB), CAT bond widening, utility outage tape
  (SO/DUK/XEL).
- Severe thunderstorm + hail belts in TX/OK/KS/IA during planting or
  harvest windows -> ag commodity spike (corn/soy/wheat ETFs DBA, WEAT,
  CORN, SOYB).
- Excessive heat advisories across ISO-NE/PJM/ERCOT -> power demand
  spike, natural-gas peaker burn (GEV, VST, CEG, NRG).
- Red-flag fire warnings in CA utility service areas -> PCW PSPS
  shutoff risk (EIX, PCG).

Source: api.weather.gov/alerts/active (no key, free, live).

Output: nws_alerts.csv
Columns: event, severity, urgency, area_desc, sender_name,
         effective, expires, headline, alert_id, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nws_alerts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.weather.gov/alerts/active"
       "?status=actual&severity=Severe,Extreme")


def main() -> None:
    req = urllib.request.Request(
        URL,
        headers={"User-Agent": UA, "Accept": "application/geo+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nws_alerts: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nws_alerts: keeping existing {OUT_CSV.name}")
        return

    feats = d.get("features", []) or []
    rows: list[dict] = []
    for f in feats:
        p = f.get("properties", {}) or {}
        event = p.get("event") or ""
        if not event:
            continue
        rows.append({
            "event": event[:80],
            "severity": p.get("severity") or "",
            "urgency": p.get("urgency") or "",
            "area_desc": (p.get("areaDesc") or "")[:180],
            "sender_name": p.get("senderName") or "",
            "effective": p.get("effective") or "",
            "expires": p.get("expires") or "",
            "headline": (p.get("headline") or "")[:200],
            "alert_id": p.get("id") or "",
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nws_alerts: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    # Most urgent first: Extreme before Severe, Immediate before Future.
    sev_rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    urg_rank = {"Immediate": 0, "Expected": 1, "Future": 2, "Past": 3}
    rows.sort(key=lambda r: (
        sev_rank.get(r["severity"], 9),
        urg_rank.get(r["urgency"], 9),
        r["event"],
    ))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["event", "severity", "urgency", "area_desc",
                  "sender_name", "effective", "expires", "headline",
                  "alert_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Count by event for summary.
    by_event: dict[str, int] = {}
    for r in rows:
        by_event[r["event"]] = by_event.get(r["event"], 0) + 1
    top = sorted(by_event.items(), key=lambda kv: -kv[1])[:3]
    top_s = ", ".join(f"{k}={v}" for k, v in top)
    extreme = sum(1 for r in rows if r["severity"] == "Extreme")
    print(f"nws_alerts: {len(rows)} alerts ({extreme} Extreme) | "
          f"top: {top_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
