#!/usr/bin/env python3
"""build_sec_geopol.py — SEC geopolitical / supply-chain exposure tape.

5 geopolitical-exposure 8-K kinds:

- ofac — OFAC sanctions disclosure (sanctions programs, denied
  persons, SDN compliance). Raw volume means most hits are boiler-
  plate risk factor language; clusters by issuer reveal real
  exposure.
- sanctions_compliance — active disclosure of sanctions-screening
  or export-control compliance.
- foreign_subsidiary — ownership/operation of a non-US subsidiary;
  proxy for geographic risk surface.
- transfer_pricing — cross-border intra-company pricing. OECD
  BEPS Pillar 2 (15% min tax, 2024) + US Section 482 adjustment
  risk. Flags potential tax surprises.
- rare_earth — rare-earth element sourcing/supply. China controls
  70% global mining, 90% processing. Export-ban headline risk.
  Names: MP/UURAF/TMC + downstream (TSLA/F/GM on magnets).

Economic readthrough:
- OFAC + sanctions_compliance cluster -> bank/FI/defense compliance
  bill (C/JPM/GS + LMT/RTX).
- Transfer-pricing cluster -> multinational tax-risk overhang.
- Rare-earth cluster -> MP upstream bullish + supply-chain
  squeeze passthrough (TSLA/F/GM auto-magnet exposure).

Source: efts.sec.gov/LATEST/search-index
Output: sec_geopol.csv

Lookback: 60 days (geopolitical disclosures arrive lumpy).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_geopol.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

QUERIES: dict[str, str] = {
    "ofac": '"OFAC"',
    "sanctions_compliance": '"sanctions compliance"',
    "foreign_subsidiary": '"foreign subsidiary"',
    "transfer_pricing": '"transfer pricing"',
    "rare_earth": '"rare earth"',
}

LIMITS = {
    "ofac": 200,
    "sanctions_compliance": 30,
    "foreign_subsidiary": 180,
    "transfer_pricing": 70,
    "rare_earth": 55,
}

TICKER_RE = re.compile(r"\(([A-Z]{1,5})\)")


def _fetch(kind: str, query: str, limit: int) -> list[dict]:
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=60)).isoformat()
    d_to = today.isoformat()
    qq = urllib.parse.quote(query)
    forms = urllib.parse.quote("8-K")
    url = (f"https://efts.sec.gov/LATEST/search-index?q={qq}"
           f"&dateRange=custom&startdt={d_from}&enddt={d_to}"
           f"&forms={forms}&from=0&size={min(limit, 100)}")
    out: list[dict] = []
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"sec_geopol: {kind} fetch failed: {e}")
        return out
    for h in d.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        names_list = src.get("display_names") or []
        names_str = " ".join(names_list)
        m = TICKER_RE.search(names_str)
        out.append({
            "kind": kind,
            "ticker": m.group(1) if m else "",
            "name": (names_list[0] if names_list else "")[:80],
            "form": src.get("form", ""),
            "filed": src.get("file_date", ""),
            "accession": h.get("_id", ""),
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for kind, q in QUERIES.items():
        batch = _fetch(kind, q, LIMITS.get(kind, 100))
        counts[kind] = len(batch)
        rows.extend(batch)
        time.sleep(0.4)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_geopol: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["filed"], r["kind"]), reverse=True)
    fieldnames = ["kind", "ticker", "name", "form", "filed",
                  "accession", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    recent = [r for r in rows if r["filed"] >= cutoff and r["ticker"]]
    tkrs = [f"{r['kind'][:4]}:{r['ticker']}" for r in recent[:15]]
    cb = " ".join(f"{k[:4]}={v}" for k, v in counts.items())
    print(f"sec_geopol: {len(rows)} rows | {cb} | "
          f"last14d={len(recent)} [{' '.join(tkrs)}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
