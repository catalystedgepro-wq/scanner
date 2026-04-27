#!/usr/bin/env python3
"""build_swpc_alerts.py — NOAA SWPC geomagnetic/radio alert feed.

Active space-weather alerts (geomagnetic storms, solar radiation,
radio blackouts). G3+ storms disrupt:
- GPS precision (DE, AGCO, DPR — precision agriculture, logistics)
- HF radio (airlines diverting polar routes: DAL, UAL, AAL)
- Power grids (utilities DUK, NEE, XEL — transformer stress)
- Pipeline telemetry (ENB, KMI, WMB)
- Satellite ops (IRDM, VSAT, GSAT, SATS)

Source: services.swpc.noaa.gov/products/alerts.json.

Output: swpc_alerts.csv
Columns: product_id, issue_datetime, kind, noaa_scale, snippet,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "swpc_alerts.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://services.swpc.noaa.gov/products/alerts.json"

SCALE_RE = re.compile(r"NOAA Scale:\s*(G\d|S\d|R\d)", re.IGNORECASE)


def _kind(pid: str) -> str:
    if not pid:
        return "other"
    p = pid.upper()
    if p.startswith("K") or p.startswith("WAT") or p.startswith("WAR"):
        return "geomag"
    if p.startswith("SUM") or p.startswith("REP"):
        return "summary"
    if p.startswith("RBF") or p.startswith("SGE"):
        return "radio"
    if p.startswith("PR") or p.startswith("SRS"):
        return "solar"
    return "other"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"swpc_alerts: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_alerts: keeping existing {OUT_CSV.name}")
        return

    if not isinstance(data, list) or not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"swpc_alerts: empty, keeping existing {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        msg = (item.get("message") or "").replace("\r", " ").replace("\n", " ")
        scale_match = SCALE_RE.search(msg)
        scale = scale_match.group(1) if scale_match else ""
        rows.append({
            "product_id": (item.get("product_id") or "")[:12],
            "issue_datetime": (item.get("issue_datetime") or "")[:19],
            "kind": _kind(item.get("product_id") or ""),
            "noaa_scale": scale[:4],
            "snippet": msg[:200],
        })

    rows.sort(key=lambda r: r["issue_datetime"], reverse=True)
    rows = rows[:300]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["product_id", "issue_datetime", "kind", "noaa_scale",
                  "snippet", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    active_scales = sum(1 for r in rows if r["noaa_scale"])
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
    print(f"swpc_alerts: {len(rows)} alerts | {breakdown} | "
          f"scaled={active_scales} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
