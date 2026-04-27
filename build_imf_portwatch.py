#!/usr/bin/env python3
"""IMF PortWatch spoke — global shipping chokepoint intelligence.

Tracks daily transit volumes through critical maritime chokepoints (Suez,
Panama, Hormuz, Bab-el-Mandeb, Bosphorus, Gibraltar, etc.). When transit
collapses (war, drought, vessel grounding, geopolitical), tankers/oil/
shipping stocks move within hours.

Source: portwatch.imf.org (IMF + Oxford-Saïd Climate Finance Group).
Public CSV/JSON exports, no auth.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "imf_portwatch.csv"
STATUS_JSON = ROOT / "imf_portwatch_status.json"
# IMF PortWatch hosts datasets on ArcGIS; the chokepoints daily transit
# dataset id is 42132aa4e2fc4d41bdaf9a445f688931_0 ("Daily Chokepoint
# Transit Calls and Trade Volume Estimates"), updated weekly Tue 9 AM ET.
# We pull JSON from the FeatureServer query endpoint which returns
# structured records (not CSV — old code path was a stale URL).
CHOKEPOINT_CSV = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&orderByFields=date+DESC&resultRecordCount=200&f=json"
)
USER_AGENT = "CatalystEdge/1.0 (opensource@example.com)"

# Watch-list chokepoints + sector exposure tags for our scoring layer.
CHOKEPOINT_SECTORS = {
    "Suez Canal": ["energy", "shipping"],
    "Panama Canal": ["shipping", "agriculture"],
    "Strait of Hormuz": ["energy"],
    "Bab el-Mandeb Strait": ["energy", "shipping"],
    "Bosphorus Strait": ["energy", "shipping"],
    "Strait of Gibraltar": ["shipping"],
    "Strait of Malacca": ["energy", "shipping", "semis_ai"],
    "English Channel": ["shipping"],
    "Strait of Dover": ["shipping"],
    "Cape of Good Hope": ["shipping", "energy"],
}


def fetch_csv() -> list[dict] | None:
    """Fetch IMF PortWatch chokepoints via ArcGIS FeatureServer JSON.
    Discovered schema (2026-04-27): date(epoch ms), portname, n_total,
    n_container, n_tanker, capacity, etc. NO YoY field — we compute
    disruption ourselves as `n_total vs 30d moving average`."""
    # We pull more rows so we can compute a rolling average per chokepoint.
    url_long = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
        "Daily_Chokepoints_Data/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&orderByFields=date+DESC"
        "&resultRecordCount=2000&f=json"
    )
    req = urllib.request.Request(url_long, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    feats = data.get("features") if isinstance(data, dict) else None
    if not feats:
        return None
    out: list[dict] = []
    for f in feats:
        attrs = f.get("attributes") or {}
        out.append({
            "portname": attrs.get("portname") or "",
            "date": attrs.get("date") or 0,
            "n_total": attrs.get("n_total") or 0,
            "n_tanker": attrs.get("n_tanker") or 0,
            "n_container": attrs.get("n_container") or 0,
            "capacity": attrs.get("capacity") or 0,
        })
    return out


def to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    now_utc = dt.datetime.now(dt.timezone.utc)
    raw = fetch_csv()
    if raw is None:
        STATUS_JSON.write_text(json.dumps({
            "status": "fetch_error",
            "ts_utc": now_utc.isoformat(),
            "note": "IMF PortWatch CSV unavailable. May need URL refresh.",
        }, indent=2))
        print("imf_portwatch: fetch error (CSV endpoint may have moved)")
        # Write empty CSV to keep downstream consumers happy.
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            f.write("timestamp_utc,chokepoint,date,transits_total,vol_growth_yoy_pct,sector_tags\n")
        return 0

    # Group by chokepoint, compute 30-day rolling average baseline + today's
    # day-over-baseline change. Disruption fires when today's n_total is
    # >=20% below the 30d average for that chokepoint.
    by_choke: dict[str, list[dict]] = {}
    for r in raw:
        name = str(r.get("portname") or "").strip()
        if not name or name not in CHOKEPOINT_SECTORS:
            continue
        by_choke.setdefault(name, []).append(r)
    rows: list[dict] = []
    for name, recs in by_choke.items():
        # Sort newest-first (already done by orderBy DESC); first row = today.
        recs.sort(key=lambda x: x.get("date", 0), reverse=True)
        if not recs:
            continue
        latest = recs[0]
        latest_n = to_float(latest.get("n_total"))
        date_raw = latest.get("date", 0)
        date_iso = ""
        if isinstance(date_raw, (int, float)) and date_raw > 0:
            try:
                date_iso = dt.datetime.fromtimestamp(int(date_raw) / 1000, dt.timezone.utc).date().isoformat()
            except Exception:
                pass
        # 30-day baseline (skip latest, average next 30 historical).
        baseline_recs = recs[1:31]
        if baseline_recs:
            baseline = sum(to_float(b.get("n_total")) for b in baseline_recs) / len(baseline_recs)
        else:
            baseline = 0
        delta_pct = ((latest_n - baseline) / baseline * 100.0) if baseline else 0.0
        sectors = ";".join(CHOKEPOINT_SECTORS[name])
        rows.append({
            "timestamp_utc": now_utc.isoformat(),
            "chokepoint": name,
            "date": date_iso,
            "transits_total": f"{latest_n:.0f}",
            "vol_growth_yoy_pct": f"{delta_pct:+.2f}",
            "sector_tags": sectors,
        })

    fields = ["timestamp_utc", "chokepoint", "date", "transits_total", "vol_growth_yoy_pct", "sector_tags"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    STATUS_JSON.write_text(json.dumps({
        "status": "ok" if rows else "empty",
        "ts_utc": now_utc.isoformat(),
        "chokepoints_matched": len(rows),
        "raw_rows": len(raw),
    }, indent=2))
    print(f"imf_portwatch: {len(rows)} chokepoint records from {len(raw)} raw rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
