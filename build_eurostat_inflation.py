#!/usr/bin/env python3
"""build_eurostat_inflation.py — Eurostat HICP annual rate by country.

Harmonized Index of Consumer Prices (HICP), annual rate of change
(prc_hicp_manr). Covers EU27 + major EU economies. Monthly.

Countries tracked:
- EU27_2020  European Union (27 members post-Brexit)
- DE         Germany  (largest EU economy)
- FR         France
- IT         Italy
- ES         Spain
- NL         Netherlands
- PL         Poland

Signal for trading:
- EU HICP > 3% = ECB hawkish pressure; fade EUFN (EU financials)
  on rate-cut delay; bid EUO (short-EUR 2x).
- DE HICP falling below EU avg for 3+ months = core-periphery
  convergence; bid EWG (Germany ETF), EZU (Eurozone).
- ES/IT HICP > 4% while FR/DE < 3% = bond-spread widening risk;
  Italian 10y BTP-Bund spread tracks to 150bps+; fade EWI, EWP.
- PL HICP > 6% = CEE-region outlier; Bank of Poland tightening
  pressure; EUR/PLN fades; bid PLN-denominated carry.

Source: ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/
        prc_hicp_manr (JSON-stat, no key).

Output: eurostat_inflation.csv
Columns: country, iso2, period, hicp_annual_pct, mom_delta,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eurostat_inflation.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/prc_hicp_manr")

COUNTRIES = [
    ("EU27_2020", "European Union"),
    ("EA20", "Euro Area"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("IT", "Italy"),
    ("ES", "Spain"),
    ("NL", "Netherlands"),
    ("PL", "Poland"),
    ("AT", "Austria"),
    ("BE", "Belgium"),
    ("PT", "Portugal"),
    ("FI", "Finland"),
    ("IE", "Ireland"),
    ("GR", "Greece"),
    ("SE", "Sweden"),
]


def _fetch() -> dict:
    geo_qs = "&".join(f"geo={c[0]}" for c in COUNTRIES)
    url = f"{BASE}?coicop=CP00&{geo_qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"eurostat_inflation: {e}")
        return {}


def main() -> None:
    d = _fetch()
    if not d:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"eurostat_inflation: keeping existing {OUT_CSV.name}")
        return

    dims = d.get("dimension", {})
    sizes = d.get("size", [])
    dim_order = d.get("id", [])
    values = d.get("value", {})
    if not values or "time" not in dims or "geo" not in dims:
        return

    # Build flat-index → (geo_idx, time_idx) translation.
    # size is in order of `id`; only geo & time are multi-valued for us.
    geo_pos = dim_order.index("geo")
    time_pos = dim_order.index("time")
    geo_size = sizes[geo_pos]
    time_size = sizes[time_pos]

    geo_idx = dims["geo"]["category"]["index"]
    geo_rev = {v: k for k, v in geo_idx.items()}
    time_idx = dims["time"]["category"]["index"]
    time_rev = {v: k for k, v in time_idx.items()}
    name_of = dict(COUNTRIES)

    # Flat index → nested index. With dims [freq,unit,coicop,geo,time]
    # and only geo/time multi, stride_geo = time_size, stride_time = 1.
    rows: list[dict] = []
    last_months = 36  # 3-year window
    min_time_idx = max(0, time_size - last_months)

    for flat_s, v in values.items():
        try:
            flat = int(flat_s)
        except ValueError:
            continue
        if v is None:
            continue
        g = (flat // time_size) % geo_size
        t = flat % time_size
        if t < min_time_idx:
            continue
        iso2 = geo_rev.get(g)
        period = time_rev.get(t)
        if not iso2 or not period:
            continue
        rows.append({
            "country": name_of.get(iso2, iso2),
            "iso2": iso2,
            "period": period,
            "hicp_annual_pct": f"{float(v):.2f}",
            "mom_delta": "",  # filled after sort
        })

    if not rows:
        return

    # Sort by iso2 then period; fill MoM delta.
    rows.sort(key=lambda r: (r["iso2"], r["period"]))
    prev_by_iso: dict[str, float] = {}
    for r in rows:
        prev = prev_by_iso.get(r["iso2"])
        cur = float(r["hicp_annual_pct"])
        r["mom_delta"] = (f"{cur - prev:+.2f}" if prev is not None
                          else "")
        prev_by_iso[r["iso2"]] = cur

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["country", "iso2", "period", "hicp_annual_pct",
                  "mom_delta", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest EU + DE + FR.
    def _latest(iso2: str) -> dict | None:
        xs = [r for r in rows if r["iso2"] == iso2]
        return xs[-1] if xs else None

    eu = _latest("EU27_2020")
    de = _latest("DE")
    fr = _latest("FR")
    eu_s = (f"EU27 {eu['period']}={eu['hicp_annual_pct']}%"
            if eu else "")
    de_s = (f"DE {de['period']}={de['hicp_annual_pct']}%"
            if de else "")
    fr_s = (f"FR {fr['period']}={fr['hicp_annual_pct']}%"
            if fr else "")
    print(f"eurostat_inflation: {len(rows)} rows | {eu_s} | {de_s} "
          f"| {fr_s} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
