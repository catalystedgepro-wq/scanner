#!/usr/bin/env python3
"""build_usgs_streamflow.py — USGS river streamflow at key commerce sites.

River-level data is a rarely-used but extremely leading signal for:

- **Inland barge commerce** (Mississippi at Thebes, St. Louis):
  low water forces barge tonnage restrictions → grain/coal shippers
  lose capacity → **bullish rail** (UNP, NSC, CSX, CP, CNI) +
  short-term **bullish diesel/refined-products demand**.

- **Western hydropower** (Columbia at The Dalles, Colorado at Lees
  Ferry): low flow → hydro output down → grid reverts to natural
  gas peakers → **bullish CEG, VST, NRG, AES**; also bullish
  thermal gen IPPs with CA/NW exposure.

- **California Central Valley agriculture** (Sacramento at Freeport):
  low flow = water restriction = ag input pullback → bearish AGCO,
  DE, MOS, CF, CTVA; bullish almond/tree-nut specialty (JJSF, PEP).

- **Colorado River compact** (Lees Ferry + Mead elevation): Lake Mead
  below 1,075 ft → federal water shortage → CA/AZ/NV urban restrictions
  hit utilities (PCG, SRE, EIX, WEC), bullish water-efficiency plays
  (WTS, XYL, AWK, WTRG).

Metrics:
- `flow_cfs_latest` — most recent daily-mean discharge (cubic ft/sec)
- `flow_cfs_avg30` — 30-day average discharge
- `pct_vs_30d_avg` — latest as % of 30d average
  - < 60% → drought stress; rail/hydro/ag signal triggered
  - > 140% → flood risk; barge/crop damage signal

Source: waterservices.usgs.gov/nwis/dv (free, no key, stdlib).
Daily-value endpoint returns 30d history JSON in ~1s per site.

Output: usgs_streamflow.csv
Columns: site_id, site_name, region, flow_cfs_latest,
flow_cfs_avg30, pct_vs_30d_avg, trade_signal, last_updated, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "usgs_streamflow.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://waterservices.usgs.gov/nwis/dv/"

# (site_id, short_name, trade_region).
SITES: list[tuple[str, str, str]] = [
    ("07022000", "Mississippi at Thebes IL",   "midwest_barge"),
    ("07010000", "Mississippi at St. Louis",   "midwest_barge"),
    ("09380000", "Colorado at Lees Ferry AZ",  "western_compact"),
    ("09428500", "Colorado at Imperial Dam",   "lower_basin"),
    ("14105700", "Columbia at The Dalles OR",  "nw_hydropower"),
    ("11447650", "Sacramento at Freeport CA",  "ca_ag"),
    ("08374550", "Rio Grande at Foster Ranch", "tx_ag"),
    ("05082500", "Red River at Grand Forks",   "plains_grain"),
    ("02232500", "St. Johns at Deland FL",     "se_citrus"),
]


def fetch_flow(site_ids: list[str]) -> dict:
    params = {
        "sites": ",".join(site_ids),
        "parameterCd": "00060",       # discharge cfs
        "statCd": "00003",            # daily mean
        "format": "json",
        "period": "P35D",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"usgs_streamflow: fetch -> {e}")
        return {}


def classify(pct: float, region: str) -> str:
    if pct == 0:
        return "no_data"
    if pct < 60:
        if region == "midwest_barge":
            return "DROUGHT_BARGE_RESTRICTION (bullish rail UNP/NSC/CSX)"
        if region in ("nw_hydropower",):
            return "HYDRO_DEFICIT (bullish gas peakers CEG/VST/NRG)"
        if region in ("western_compact", "lower_basin"):
            return "COMPACT_STRESS (bullish water eff WTS/XYL/AWK)"
        if region in ("ca_ag", "tx_ag", "plains_grain", "se_citrus"):
            return "AG_STRESS (bearish AGCO/DE; bullish grain MOS/CF)"
        return "DROUGHT"
    if pct > 140:
        return "FLOOD_RISK (barge/crop damage)"
    return "normal"


def main() -> None:
    data = fetch_flow([s[0] for s in SITES])
    if not data:
        return

    series = data.get("value", {}).get("timeSeries", []) or []
    by_site: dict[str, list[tuple[str, float]]] = {}
    for s in series:
        site_code = (
            s.get("sourceInfo", {}).get("siteCode", [{}])[0].get("value", "")
        )
        values = (s.get("values", [{}])[0] or {}).get("value", []) or []
        by_site[site_code] = []
        for v in values:
            try:
                val = float(v.get("value", "-999999"))
            except (ValueError, TypeError):
                continue
            if val < 0:
                continue
            by_site[site_code].append((v.get("dateTime", ""), val))

    rows: list[dict] = []
    for site_id, short, region in SITES:
        hist = by_site.get(site_id, [])
        if not hist:
            continue
        hist.sort(key=lambda t: t[0])
        flows = [v for _, v in hist]
        latest_ts, latest = hist[-1]
        avg30 = sum(flows) / len(flows) if flows else 0.0
        pct = (latest / avg30 * 100.0) if avg30 else 0.0

        rows.append({
            "site_id": site_id,
            "site_name": short,
            "region": region,
            "flow_cfs_latest": f"{latest:.0f}",
            "flow_cfs_avg30": f"{avg30:.0f}",
            "pct_vs_30d_avg": f"{pct:.1f}",
            "trade_signal": classify(pct, region),
            "last_updated": latest_ts,
        })

    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"usgs_streamflow: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort: stressed sites first (low pct), then flood, then normal.
    def _stress(r):
        try:
            pct = float(r["pct_vs_30d_avg"])
        except ValueError:
            return 999.0
        return abs(pct - 100.0) * -1  # largest deviation first
    rows.sort(key=_stress)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["site_id", "site_name", "region", "flow_cfs_latest",
                  "flow_cfs_avg30", "pct_vs_30d_avg", "trade_signal",
                  "last_updated", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    stressed = [r for r in rows
                if r["trade_signal"] not in ("normal", "no_data")]
    hi = rows[0] if rows else None
    hi_s = (f"{hi['site_name']}={hi['pct_vs_30d_avg']}% ({hi['trade_signal']})"
            if hi else "")
    print(f"usgs_streamflow: {len(rows)} sites | {len(stressed)} stressed | "
          f"lead: {hi_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
