#!/usr/bin/env python3
"""build_global_heatmap.py — continent → country → sector → ticker drill-down.

Derived from intl_equity_gappers.csv. Output: docs/data/global_heatmap.json
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def _find_root() -> Path:
    for cand in (Path("/opt/catalyst"),
                 Path("/home/operator/.openclaw/workspace"),
                 Path(__file__).resolve().parent):
        if (cand / "build_global_heatmap.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
GAPPERS = ROOT / "docs/intl_equity_gappers.csv"
OUT = ROOT / "docs/data/global_heatmap.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Continent grouping (ISO-3 → continent bucket)
CONTINENT = {
    # Americas
    "USA": "Americas", "CAN": "Americas", "MEX": "Americas",
    "BRA": "Americas", "ARG": "Americas", "CHL": "Americas",
    "COL": "Americas", "PER": "Americas",
    # Europe
    "GBR": "Europe", "DEU": "Europe", "FRA": "Europe", "CHE": "Europe",
    "NLD": "Europe", "ESP": "Europe", "ITA": "Europe", "SWE": "Europe",
    "NOR": "Europe", "DNK": "Europe", "FIN": "Europe", "BEL": "Europe",
    "AUT": "Europe", "IRL": "Europe", "PRT": "Europe", "GRC": "Europe",
    "POL": "Europe", "CZE": "Europe", "HUN": "Europe", "RUS": "Europe",
    # Asia
    "JPN": "Asia", "CHN": "Asia", "HKG": "Asia", "TWN": "Asia",
    "KOR": "Asia", "IND": "Asia", "SGP": "Asia", "THA": "Asia",
    "IDN": "Asia", "MYS": "Asia", "PHL": "Asia", "VNM": "Asia",
    # Oceania
    "AUS": "Oceania", "NZL": "Oceania",
    # Africa
    "ZAF": "Africa", "NGA": "Africa", "KEN": "Africa",
    "MAR": "Africa", "EGY": "Africa", "BWA": "Africa",
    "TUN": "Africa", "GHA": "Africa", "CIV": "Africa",
    # MENA (Middle East / North Africa minus Africa)
    "ISR": "MENA", "TUR": "MENA", "ARE": "MENA",
    "QAT": "MENA", "SAU": "MENA",
    # Frontier other
    "PAK": "Asia", "KAZ": "Asia",
}


def _f(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not GAPPERS.exists():
        print(f"missing {GAPPERS}")
        return 1

    rows = []
    with GAPPERS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    # Build nested aggregation: continent → country → sector → tickers
    cont_map = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        iso = r.get("country_iso", "")
        cont = CONTINENT.get(iso, "Other")
        country_name = r.get("country_full", "") or iso
        sector = r.get("sector_gics", "") or "Other"
        cont_map[cont][(iso, country_name)][sector].append({
            "ticker": r["ticker"],
            "name": r.get("name", ""),
            "gap_pct": _f(r.get("gap_pct")),
            "vol_ratio": _f(r.get("vol_ratio_20d")),
            "regime": r.get("regime", ""),
        })

    continents = []
    for cont_name, country_dict in cont_map.items():
        all_gaps = []
        countries = []
        country_ticker_count = 0
        for (iso, cname), sec_dict in country_dict.items():
            country_gaps = []
            sectors_list = []
            for sec_name, tickers in sec_dict.items():
                tg = [t["gap_pct"] for t in tickers]
                country_gaps.extend(tg)
                tickers.sort(key=lambda t: -abs(t["gap_pct"]))
                sectors_list.append({
                    "name": sec_name,
                    "avg_gap": round(sum(tg)/len(tg), 2) if tg else 0,
                    "ticker_count": len(tickers),
                    "top_mover": tickers[0]["ticker"] if tickers else "",
                    "tickers": tickers[:5],
                })
            sectors_list.sort(key=lambda s: -abs(s["avg_gap"]))
            countries.append({
                "country_iso": iso,
                "country_name": cname,
                "avg_gap": round(sum(country_gaps)/len(country_gaps), 2) if country_gaps else 0,
                "ticker_count": len(country_gaps),
                "top_mover": max(
                    (t for s in sec_dict.values() for t in s),
                    key=lambda t: abs(t["gap_pct"]),
                    default={"ticker": ""},
                ).get("ticker", ""),
                "sectors": sectors_list,
            })
            country_ticker_count += len(country_gaps)
            all_gaps.extend(country_gaps)
        countries.sort(key=lambda c: -abs(c["avg_gap"]))
        continents.append({
            "name": cont_name,
            "avg_gap": round(sum(all_gaps)/len(all_gaps), 2) if all_gaps else 0,
            "ticker_count": country_ticker_count,
            "country_count": len(countries),
            "countries": countries,
        })
    continents.sort(key=lambda c: -abs(c["avg_gap"]))

    payload = {
        "generated_at": captured,
        "continent_count": len(continents),
        "country_count": sum(c["country_count"] for c in continents),
        "ticker_count": sum(c["ticker_count"] for c in continents),
        "continents": continents,
    }
    OUT.write_text(json.dumps(payload, indent=2))

    print(f"global_heatmap: {len(continents)} continents | "
          f"countries={payload['country_count']} | "
          f"tickers={payload['ticker_count']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
