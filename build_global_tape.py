#!/usr/bin/env python3
"""build_global_tape.py — aggregate all per-country panels into one
unified chronological catalyst tape rendered on /international/.

Reads per-country panels (asx, rns, hkex, tdnet, cvm, kind, bafin, nse,
bmv, africa, sgx, twse) and merges into docs/data/global_tape.json.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def _find_root() -> Path:
    for cand in (Path("/opt/catalyst"),
                 Path("/home/operator/.openclaw/workspace"),
                 Path(__file__).resolve().parent):
        if (cand / "build_global_tape.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
DATA = ROOT / "docs/data"
OUT = DATA / "global_tape.json"

PANEL_FILES = [
    "asx_panels.json", "rns_panels.json", "hkex_panels.json",
    "tdnet_panels.json", "cvm_panels.json", "kind_panels.json",
    "bafin_panels.json", "nse_panels.json", "bmv_panels.json",
    "africa_panels.json", "sgx_panels.json", "twse_panels.json",
]

FLAG = {
    "AUS": "🇦🇺", "GBR": "🇬🇧", "HKG": "🇭🇰", "JPN": "🇯🇵",
    "BRA": "🇧🇷", "KOR": "🇰🇷", "DEU": "🇩🇪", "IND": "🇮🇳",
    "MEX": "🇲🇽", "ZAF": "🇿🇦", "NGA": "🇳🇬", "KEN": "🇰🇪",
    "MAR": "🇲🇦", "EGY": "🇪🇬", "SGP": "🇸🇬", "TWN": "🇹🇼",
}


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    all_rows: list[dict] = []
    by_country: dict = defaultdict(int)
    by_kind: dict = defaultdict(int)

    for fname in PANEL_FILES:
        p = DATA / fname
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        recent = d.get("recent") or d.get("top_inside_info") or []
        for r in recent:
            iso = r.get("country_iso") or r.get("country") or ""
            row = {
                "ticker": r.get("ticker") or r.get("symbol") or "",
                "company": r.get("company") or r.get("name") or "",
                "country_iso": iso,
                "exchange": r.get("exchange") or "",
                "headline": (r.get("headline") or r.get("title") or "")[:200],
                "kind": r.get("kind") or "other",
                "issued_at": r.get("issued_at") or r.get("date") or "",
                "url": r.get("url") or "",
                "publisher": r.get("publisher") or "",
                "flag": FLAG.get(iso, ""),
                "_source": fname.replace("_panels.json", ""),
            }
            if not row["ticker"] or not row["headline"]:
                continue
            all_rows.append(row)
            by_country[iso] += 1
            by_kind[row["kind"]] += 1

    # Sort by issued_at desc; rows missing timestamps fall to bottom
    def sort_key(r):
        ts = r.get("issued_at") or ""
        return ts
    all_rows.sort(key=sort_key, reverse=True)

    payload = {
        "generated_at": captured,
        "count": len(all_rows),
        "sources_merged": len([f for f in PANEL_FILES if (DATA / f).exists()]),
        "by_country": dict(by_country),
        "by_kind": dict(by_kind),
        "recent": all_rows[:200],
    }
    OUT.write_text(json.dumps(payload, indent=2))

    top_countries = sorted(by_country.items(), key=lambda x: -x[1])[:5]
    top_kinds = sorted(by_kind.items(), key=lambda x: -x[1])[:5]
    print(f"global_tape: {len(all_rows)} aggregated rows | "
          f"sources={payload['sources_merged']} | "
          f"top_countries={top_countries} | top_kinds={top_kinds}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
