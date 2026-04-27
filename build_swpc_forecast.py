#!/usr/bin/env python3
"""build_swpc_forecast.py — NOAA SWPC 3-day Kp forecast + F10.7 flux.

Forward-looking space weather:
- 3-day Kp forecast (observed + predicted geomag activity)
- F10.7 cm solar radio flux (satellite drag proxy)

Distinguishes 'active now' (swpc_kp) from 'active next 72h' (this
spoke). Forward Kp ≥ 5 within 48h primes:
- Airlines on polar reroutes (DAL, UAL, AAL)
- Satellite ops (STRL, VSAT, IRDM) pre-positioning
- Utility grid operators
- Defense GPS users

Source: services.swpc.noaa.gov (NOAA SWPC).

Output: swpc_forecast.csv
Columns: series, time_tag, value, noaa_scale, observed, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "swpc_forecast.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KP_URL = ("https://services.swpc.noaa.gov/products/"
          "noaa-planetary-k-index-forecast.json")
F107_URL = "https://services.swpc.noaa.gov/json/f107_cm_flux.json"


def _fetch(url: str) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"swpc_forecast {url[-40:]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    kp_raw = _fetch(KP_URL)
    if isinstance(kp_raw, list) and kp_raw:
        first = kp_raw[0]
        if isinstance(first, dict):
            for item in kp_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    kp_val = float(item.get("kp") or 0)
                except (TypeError, ValueError):
                    continue
                rows.append({
                    "series": "kp_3day_forecast",
                    "time_tag": str(item.get("time_tag") or "")[:19],
                    "value": f"{kp_val:.2f}",
                    "noaa_scale": str(item.get("noaa_scale") or "")[:4],
                    "observed": str(item.get("observed") or "")[:10],
                })
        elif isinstance(first, list) and len(kp_raw) > 1:
            for item in kp_raw[1:]:
                if not isinstance(item, list) or len(item) < 3:
                    continue
                try:
                    kp_val = float(item[1])
                except (TypeError, ValueError):
                    continue
                rows.append({
                    "series": "kp_3day_forecast",
                    "time_tag": str(item[0])[:19],
                    "value": f"{kp_val:.2f}",
                    "noaa_scale": str(item[3] or "")[:4] if len(item) > 3 else "",
                    "observed": str(item[2])[:10] if len(item) > 2 else "",
                })

    f107 = _fetch(F107_URL)
    if isinstance(f107, list):
        for item in f107[:200]:
            if not isinstance(item, dict):
                continue
            try:
                flux = float(item.get("flux") or 0)
            except (TypeError, ValueError):
                continue
            rows.append({
                "series": "f107_cm_flux",
                "time_tag": str(item.get("time_tag") or "")[:19],
                "value": f"{flux:.1f}",
                "noaa_scale": "",
                "observed": str(item.get("reporting_schedule") or "")[:14],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_forecast: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["series"], r["time_tag"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["series", "time_tag", "value", "noaa_scale",
                  "observed", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kp_rows = [r for r in rows if r["series"] == "kp_3day_forecast"]
    f107_rows = [r for r in rows if r["series"] == "f107_cm_flux"]
    max_kp = max((float(r["value"]) for r in kp_rows), default=0)
    latest_f107 = f107_rows[-1]["value"] if f107_rows else "?"
    print(f"swpc_forecast: {len(rows)} points | kp_forecast="
          f"{len(kp_rows)} (peak {max_kp:.1f}) | f107={len(f107_rows)} "
          f"(latest {latest_f107}) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
