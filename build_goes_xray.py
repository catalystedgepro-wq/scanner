#!/usr/bin/env python3
"""build_goes_xray.py — NOAA GOES X-ray 3-day flux time series.

Supplements build_space_weather.py with high-resolution solar X-ray flux
from GOES-16/18 satellites. X-class flares (>= 1e-4 W/m^2) correlate with:

- Satellite outages  -> IRDM, GSAT, VSAT (communications), LMT, NOC
  (defense space assets), GPS signal degradation hurts precision-ag
  (DE, AGCO) and logistics (FDX, UPS)
- Power grid surges  -> regulated utilities (DUK, SO, NEE) face
  transformer-stress incidents; XEL, AEP at higher geomagnetic latitudes
- Aviation rerouting -> polar routes diverted, fuel cost impact
  (DAL, UAL, AAL on transpolar Asia flights)
- HF radio blackout  -> maritime/Coast Guard ops, emergency response
- Space tourism / launch delays -> SpaceX, RKLB, ASTR (Starlink adds)

Source: services.swpc.noaa.gov (NOAA Space Weather Prediction Center).

Output: goes_xray.csv
Columns: time_tag, satellite, flux, observed_flux, flare_class,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "goes_xray.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-3-day.json"


def _flare_class(flux: float) -> str:
    """NOAA flare classification from long-channel flux (W/m^2)."""
    if flux >= 1e-4:
        return f"X{flux / 1e-4:.1f}"
    if flux >= 1e-5:
        return f"M{flux / 1e-5:.1f}"
    if flux >= 1e-6:
        return f"C{flux / 1e-6:.1f}"
    if flux >= 1e-7:
        return f"B{flux / 1e-7:.1f}"
    if flux >= 1e-8:
        return f"A{flux / 1e-8:.1f}"
    return "—"


def _fetch() -> list | None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"goes_xray: {e}")
        return None


def main() -> None:
    data = _fetch()
    if not data or not isinstance(data, list):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"goes_xray: no data, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tt = item.get("time_tag") or ""
        sat = item.get("satellite") or ""
        flux_raw = item.get("flux")
        obs_raw = item.get("observed_flux")
        try:
            flux = float(flux_raw) if flux_raw is not None else 0.0
        except (TypeError, ValueError):
            flux = 0.0
        try:
            obs = float(obs_raw) if obs_raw is not None else 0.0
        except (TypeError, ValueError):
            obs = 0.0
        rows.append({
            "time_tag": tt[:20],
            "satellite": str(sat)[:6],
            "flux": f"{flux:.3e}",
            "observed_flux": f"{obs:.3e}",
            "flare_class": _flare_class(max(flux, obs)),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"goes_xray: empty, keeping existing {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["time_tag"], reverse=True)
    rows = rows[:600]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["time_tag", "satellite", "flux", "observed_flux",
                  "flare_class", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    peak = max(rows, key=lambda r: float(r["flux"]))
    classes: dict[str, int] = {}
    for r in rows:
        c = r["flare_class"][:1] if r["flare_class"] != "—" else "—"
        classes[c] = classes.get(c, 0) + 1
    cls_str = " ".join(f"{k}={v}" for k, v in sorted(classes.items()))
    print(f"goes_xray: {len(rows)} samples | peak "
          f"{peak['flare_class']} @ {peak['time_tag']} | {cls_str} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
