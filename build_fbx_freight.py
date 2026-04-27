#!/usr/bin/env python3
"""build_fbx_freight.py — Freightos Baltic Index (FBX) container rates.

FBX is a free daily container shipping spot-rate index on 12+ major
trade lanes (Asia-Europe, Asia-US, Europe-US, etc.). Container rates
lead goods inflation by ~4-6 weeks (CPI goods component) and directly
drive ocean-shipping equity earnings (ZIM, MATX, SBLK, GOGL, DAC).

Signal:
- FBX01 Global trending up > +10% 4-wk = supply chain tightening →
  inflation impulse in next CPI print (Fed hawkish reaction risk)
- FBX03 Asia-US-W Coast spike = China export surge / pull-forward on
  tariff risk (retail inventory build, HOLIDAY EARLY)
- FBX11 Asia-US-E Coast > FBX03 by >$500 = Panama/Red Sea disruption
  (chokepoint risk → USO, BDRY, DSX beneficiaries)
- FBX01 down -15% QoQ = excess capacity / demand decel (ZIM, MATX
  earnings pressure)

Drives:
- Container shipping equities (ZIM, MATX, SBLK, GOGL, DAC, CMRE, SFL)
- Port infrastructure (GWW, FAST, KNX)
- Retail with ocean freight exposure (COST, WMT, TGT, DLTR)
- Inflation via CPI goods (TIP, SCHP, LQD/HYG regime)

Source: freightos.com/enterprise/terminal/freightos-baltic-index-
global-container-pricing-index/ (HTML embed, free, daily).
Output: fbx_freight.csv
Columns: lane, code, value_usd, change_pct, direction, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "fbx_freight.csv"

UA = ("Mozilla/5.0 (compatible; CatalystEdge/1.0; "
      "+opensource@example.com)")
URL = ("https://fbx.freightos.com/")

LANE_NAMES = {
    "FBX01": "Global composite",
    "FBX02": "Asia → North Europe (West)",
    "FBX03": "Asia → US West Coast",
    "FBX04": "Asia → Mediterranean",
    "FBX11": "Asia → US East Coast",
    "FBX12": "North Europe → Asia",
    "FBX13": "Europe → US East Coast",
    "FBX14": "Europe → South America",
    "FBX21": "US East Coast → North Europe",
    "FBX22": "US West Coast → Asia",
    "FBX24": "North Europe → US East Coast",
}

# Matches: FBX01","value":"$2,653","change":"+6.64%","positive":true
ROW_RE = re.compile(
    r'(FBX\d{2})[\"\'][^{]*?[\"\']value[\"\'][^\"\']*[\"\']([\$0-9,.]+)[\"\']'
    r'[^{]*?[\"\']change[\"\'][^\"\']*[\"\']([\-+0-9.]+%)[\"\']'
    r'[^{]*?[\"\']positive[\"\'][^\"\']*(true|false)'
)


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"fbx_freight: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fbx_freight: keeping existing {OUT_CSV.name}")
        return

    matches = ROW_RE.findall(html)
    if not matches:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"fbx_freight: no FBX blocks parsed, keeping "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    rows: list[dict] = []
    seen: set[str] = set()
    for code, value, change, positive in matches:
        if code in seen:
            continue
        seen.add(code)
        val = value.replace("$", "").replace(",", "")
        try:
            val_f = float(val)
        except ValueError:
            continue
        direction = "up" if positive == "true" else "down"
        rows.append({
            "lane": LANE_NAMES.get(code, code),
            "code": code,
            "value_usd": f"{val_f:.0f}",
            "change_pct": change,
            "direction": direction,
            "captured_at": now,
        })

    if not rows:
        return

    rows.sort(key=lambda r: r["code"])
    fieldnames = ["lane", "code", "value_usd", "change_pct", "direction",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    glob = next((r for r in rows if r["code"] == "FBX01"), None)
    asia_wc = next((r for r in rows if r["code"] == "FBX03"), None)
    asia_ec = next((r for r in rows if r["code"] == "FBX11"), None)
    bits: list[str] = []
    if glob:
        bits.append(f"Global=${glob['value_usd']}({glob['change_pct']})")
    if asia_wc:
        bits.append(f"Asia-WC=${asia_wc['value_usd']}")
    if asia_ec:
        bits.append(f"Asia-EC=${asia_ec['value_usd']}")
    print(f"fbx_freight: {len(rows)} lanes | {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
