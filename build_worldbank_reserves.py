#!/usr/bin/env python3
"""build_worldbank_reserves.py — FX reserves + current-account cross-country.

World Bank Open Data FI.RES.TOTL.CD (total reserves incl. gold USD)
and BN.CAB.XOKA.CD (current-account balance USD) for major economies.

Reserve adequacy is a sovereign-risk and EM-stability signal:
- Falling reserves while C/A deficit widens → pressure on currency
- Rising reserves → accumulating USD (typical for CN, JP, SA)
- Russia/Turkey reserve crashes have preceded ruble/lira collapses

Signal use:
- EM FX volatility premium
- Sovereign CDS readthrough (MSCI EM bonds)
- Commodity exporter relative-value (SA, BR, MX, RU reserves vs
  oil/iron-ore cycles)

Source: api.worldbank.org/v2/country/.../indicator/...
Output: worldbank_reserves.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "worldbank_reserves.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
COUNTRIES = "JP;CN;IN;RU;KR;BR;MX;SA;IL;TR;ZA;DE;FR;GB;CA;AU;US"
BASE = ("https://api.worldbank.org/v2/country/{cty}/indicator/{ind}"
        "?format=json&date=2021:2025&per_page=400")

INDICATORS = {
    "reserves_usd": "FI.RES.TOTL.CD",
    "current_account_usd": "BN.CAB.XOKA.CD",
}


def _get_json(url: str) -> list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
        if isinstance(d, list) and len(d) >= 2:
            return d[1] if isinstance(d[1], list) else None
    except Exception as e:
        print(f"worldbank_reserves: {url[-30:]}: {e}")
    return None


def main() -> None:
    by_country_year: dict[tuple[str, str], dict[str, float]] = {}
    country_names: dict[str, str] = {}

    for key, ind in INDICATORS.items():
        url = BASE.format(cty=COUNTRIES, ind=ind)
        entries = _get_json(url)
        if not entries:
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            cty = e.get("countryiso3code", "") or (
                e.get("country", {}).get("id", "")
                if isinstance(e.get("country"), dict) else "")
            if not cty:
                continue
            year = e.get("date", "")
            val = e.get("value")
            if val is None:
                continue
            cname = (e.get("country", {}).get("value", "")
                     if isinstance(e.get("country"), dict) else cty)
            country_names[cty] = cname
            by_country_year.setdefault((cty, year), {})[key] = (
                float(val))

    if not by_country_year:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"worldbank_reserves: no fetch, keeping "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for (cty, year), vals in by_country_year.items():
        rows.append({
            "country_iso3": cty,
            "country_name": country_names.get(cty, ""),
            "year": year,
            "reserves_usd_bn": (
                f"{vals['reserves_usd'] / 1e9:.2f}"
                if "reserves_usd" in vals else ""),
            "current_account_usd_bn": (
                f"{vals['current_account_usd'] / 1e9:.2f}"
                if "current_account_usd" in vals else ""),
            "captured_at": now_iso,
        })

    rows.sort(key=lambda r: (r["country_iso3"], r["year"]))

    fieldnames = ["country_iso3", "country_name", "year",
                  "reserves_usd_bn", "current_account_usd_bn",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_by_cty: dict[str, dict] = {}
    for r in rows:
        if r["reserves_usd_bn"]:
            prev = latest_by_cty.get(r["country_iso3"])
            if not prev or r["year"] > prev["year"]:
                latest_by_cty[r["country_iso3"]] = r
    top = sorted(latest_by_cty.values(),
                 key=lambda r: float(r["reserves_usd_bn"] or 0),
                 reverse=True)[:5]
    summary = " ".join(f"{r['country_iso3']}={r['reserves_usd_bn']}B"
                       for r in top)
    print(f"worldbank_reserves: {len(rows)} rows | "
          f"top_reserves[{summary}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
