#!/usr/bin/env python3
"""build_space_weather.py — NOAA SWPC geomagnetic + solar activity.

Space weather drives three niche but high-beta equity reactions:
- **Satellite operators**: IRDM (Iridium), VSAT (Viasat), MAXR
  (MAXAR/Maxar now private), ROK (Rockwell Collins), plus commercial
  Starlink-adjacent plays. G4/G5 events cause LEO-orbit degradation +
  revenue-hit warnings.
- **Grid/utility**: AEP, SO, DUK vulnerability to geomagnetically
  induced currents (GIC) on high-latitude transformers. Hydro-Québec
  1989 precedent (9h blackout) — risk model still cited by insurers.
- **Airlines**: UAL, DAL polar-route GPS/comms disruption, longer
  reroutes → Q3-Q4 fuel-cost watch.
- **Mining/drilling**: Gyro drilling precision degrades during storms;
  watch SLB, HAL on polar-ops exposure.

Trade uses:
- G4+ geomagnetic storm watch issued: short IRDM, long small utility
  ETFs defensively, 1-2 day window.
- X-class solar flare probability > 30% AND M-class > 50% for 1 day
  ahead: elevated VIX-risk narrative for satellite complex.
- K-index sustained ≥ 7 for 6+ hours: extreme event, equity complex
  re-prices on 2-3 day lag as news propagates.

Source: services.swpc.noaa.gov (free, no key).
- /json/planetary_k_index_1m.json — 1-min realtime K (most recent pt)
- /products/noaa-planetary-k-index.json — 3-hour historical K (7 days)
- /products/alerts.json — active Space Weather Messages (G/S/R alerts)
- /json/solar_probabilities.json — 3-day X-class/M-class/protons fcst

Output: space_weather.csv
Columns: metric, value, scale_level, issued_at, message, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "space_weather.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://services.swpc.noaa.gov"


def fetch_json(path: str) -> list | dict | None:
    req = urllib.request.Request(f"{BASE}{path}",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"space_weather: {path} -> {e}")
        return None


def _g_scale(kp: float) -> str:
    if kp >= 9: return "G5"
    if kp >= 8: return "G4"
    if kp >= 7: return "G3"
    if kp >= 6: return "G2"
    if kp >= 5: return "G1"
    return ""


def main() -> None:
    rows: list[dict] = []

    # 1. Current Kp (latest 1-min observation)
    k_now = fetch_json("/json/planetary_k_index_1m.json") or []
    if isinstance(k_now, list) and k_now:
        latest = k_now[-1]
        kp = float(latest.get("estimated_kp") or latest.get("kp_index") or 0)
        rows.append({
            "metric": "kp_current",
            "value": f"{kp:.2f}",
            "scale_level": _g_scale(kp),
            "issued_at": latest.get("time_tag", ""),
            "message": f"Planetary K-index now {kp:.2f}",
        })

    # 2. Recent max Kp (7-day 3-hour history)
    k_hist = fetch_json("/products/noaa-planetary-k-index.json") or []
    if isinstance(k_hist, list) and k_hist:
        max_pt = max(k_hist, key=lambda p: float(p.get("Kp", 0)))
        mx = float(max_pt.get("Kp", 0))
        rows.append({
            "metric": "kp_max_7d",
            "value": f"{mx:.2f}",
            "scale_level": _g_scale(mx),
            "issued_at": max_pt.get("time_tag", ""),
            "message": f"Max Kp over past 7 days = {mx:.2f}",
        })

    # 3. Active alerts (filter to G/S/R warnings, not routine advisories)
    alerts = fetch_json("/products/alerts.json") or []
    if isinstance(alerts, list):
        geomag = [a for a in alerts if isinstance(a, dict) and (
            "ALTK" in (a.get("product_id") or "")
            or "G" in (a.get("message") or "")[:300]
        )][:5]
        for a in geomag:
            msg = (a.get("message") or "").replace("\r\n", " ")[:200]
            scale = ""
            for lvl in ("G5", "G4", "G3", "G2", "G1", "S4", "S3", "R3"):
                if lvl in msg:
                    scale = lvl
                    break
            rows.append({
                "metric": "alert",
                "value": a.get("product_id", ""),
                "scale_level": scale,
                "issued_at": a.get("issue_datetime", ""),
                "message": msg,
            })

    # 4. 3-day solar flare probabilities
    solar = fetch_json("/json/solar_probabilities.json") or []
    if isinstance(solar, list) and solar:
        today = solar[0]
        rows.append({
            "metric": "flare_1d_M",
            "value": str(today.get("m_class_1_day", "")),
            "scale_level": "",
            "issued_at": today.get("date", ""),
            "message": f"M-class flare prob 1-day = {today.get('m_class_1_day','?')}%",
        })
        rows.append({
            "metric": "flare_1d_X",
            "value": str(today.get("x_class_1_day", "")),
            "scale_level": "",
            "issued_at": today.get("date", ""),
            "message": f"X-class flare prob 1-day = {today.get('x_class_1_day','?')}%",
        })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 150:
        print(f"space_weather: no new data, keeping existing "
              f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["metric", "value", "scale_level", "issued_at",
                        "message", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Summary line
    cur = next((r for r in rows if r["metric"] == "kp_current"), None)
    mx = next((r for r in rows if r["metric"] == "kp_max_7d"), None)
    alert_count = sum(1 for r in rows if r["metric"] == "alert")
    cur_s = f"Kp={cur['value']} ({cur['scale_level'] or 'calm'})" if cur else "Kp=?"
    mx_s = f"7d max Kp={mx['value']} ({mx['scale_level'] or 'calm'})" if mx else ""
    print(f"space_weather: {len(rows)} metrics | {cur_s} | {mx_s} | "
          f"{alert_count} alerts -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
