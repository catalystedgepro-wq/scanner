#!/usr/bin/env python3
"""build_bpa_balancing.py — Bonneville Power Administration load + wind.

BPA is the federal power marketer for the Pacific Northwest — biggest
hydropower + wind balancing authority in the West. Covers OR, WA, ID,
parts of MT. Reads directly onto AMZN Oregon datacenter cluster.

Signal:
- Wind MW ramp = PacNW renewables dev cadence (NEE, GEV)
- Load MW vs prior week = AMZN/MSFT/GOOG AWS/Azure Oregon datacenter draw
- Oversupply mitigation = spilled hydro (=free zero-cost MWh dispatch)
- Base schedule vs generation = grid flex capacity

Sources:
  transmission.bpa.gov/Business/Operations/Wind/baltwg.txt (5-min Load+Wind)
  transmission.bpa.gov/business/operations/Wind/twndbspt.txt
Output: bpa_balancing.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bpa_balancing.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def _get(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"bpa_balancing: {url}: {e}")
        return None


def _parse_tab(txt: str) -> tuple[list[str], list[list[str]]]:
    """BPA publishes tab-delimited txt with a preamble + BPA_FORECAST section."""
    lines = txt.splitlines()
    # Find the header line — the first line starting with 'Date/Time'
    hdr_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("Date/Time"):
            hdr_idx = i
            break
    if hdr_idx is None:
        return [], []
    header = [h.strip() for h in lines[hdr_idx].split("\t")]
    data: list[list[str]] = []
    for ln in lines[hdr_idx + 1:]:
        if not ln.strip():
            continue
        cells = ln.split("\t")
        # Cells must have at least the date + 1 value.
        if len(cells) < 2:
            continue
        if not cells[0].strip():
            continue
        data.append([c.strip() for c in cells])
    return header, data


def _last_complete(header: list[str], data: list[list[str]]) -> dict | None:
    # Walk bottom up, find last row where all numeric cols have a value.
    for row in reversed(data):
        parsed = {}
        ok = False
        for i, col in enumerate(header):
            if i >= len(row):
                break
            v = row[i].strip()
            parsed[col] = v
            if col != "Date/Time" and v and v not in ("-", ""):
                ok = True
        if ok:
            return parsed
    return None


def main() -> None:
    bal_txt = _get(
        "https://transmission.bpa.gov/Business/Operations/Wind/baltwg.txt")
    if not bal_txt:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bpa_balancing: no fetch, keeping {OUT_CSV.name}")
        return

    header, data = _parse_tab(bal_txt)
    if not header or not data:
        return

    lat = _last_complete(header, data)
    if not lat:
        return

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now_iso = now_iso.replace("+00:00", "Z")

    rows: list[dict] = []
    snap_time = lat.get("Date/Time", "")
    for col, val in lat.items():
        if col == "Date/Time":
            continue
        if not val or val in ("-",):
            continue
        try:
            mw = float(val)
        except Exception:
            continue
        rows.append({
            "metric": col.lower().replace(" ", "_"),
            "value": f"{mw:.1f}",
            "unit": "MW",
            "snapshot_time": snap_time,
            "captured_at": now_iso,
        })

    if not rows:
        return

    fieldnames = ["metric", "value", "unit", "snapshot_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    bymet = {r["metric"]: float(r["value"]) for r in rows}
    bits = []
    for k in ("load", "total_wind_generation", "hydro", "total_thermal",
              "fossil/biomass"):
        if k in bymet:
            bits.append(f"{k}={bymet[k]/1000:.2f}GW")
    print(f"bpa_balancing: {len(rows)} rows | {snap_time} | {' '.join(bits)} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
