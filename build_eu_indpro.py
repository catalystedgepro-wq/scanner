#!/usr/bin/env python3
"""build_eu_indpro.py — Eurostat EU27 industrial production (STS).

EU industrial production is the single best leading indicator for:
- European cyclical earnings (SIE, BASF, ASML capex timing)
- EU auto demand (VOW, BMW, P911, STLA)
- Global PMI read-through (leads US ISM by ~45 days)
- FX rate EUR/USD conditional on ECB reaction

Signal:
- MoM drop in EU27 → EU cyclical underperformance begins
- DE deviation vs EU → German manufacturing recession divergence
- IT/ES vs EU → peripheral vs core divergence

Source: ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inpr_m
Output: eu_indpro.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "eu_indpro.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/"
        "data/sts_inpr_m")

GEOS = ["EU27_2020", "EA20", "DE", "FR", "IT", "ES", "NL", "BE",
        "PL", "GR", "SE", "PT"]


def _get(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"eu_indpro: {url[:100]}: {e}")
        return None


def main() -> None:
    params = (
        "?s_adj=CA&lastTimePeriod=18"
        f"&{'&'.join(f'geo={g}' for g in GEOS)}"
        "&nace_r2=B-D&unit=I21")
    data = _get(BASE + params)
    if not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"eu_indpro: no fetch, keeping {OUT_CSV.name}")
        return

    dim = data.get("dimension", {})
    size = data.get("size", [])
    vals = data.get("value", {})
    if not dim or not size or not vals:
        return

    geo_idx = dim.get("geo", {}).get("category", {}).get("index", {})
    geo_lbl = dim.get("geo", {}).get("category", {}).get("label", {})
    time_idx = dim.get("time", {}).get("category", {}).get("index", {})
    time_lbl = dim.get("time", {}).get("category", {}).get("label", {})
    geo_size = size[-2]
    time_size = size[-1]

    # Build inverse idx→key for fast decode.
    idx_to_geo = {v: k for k, v in geo_idx.items()}
    idx_to_time = {v: k for k, v in time_idx.items()}

    # Flat-index decode: flat = g*time_size + t.
    per_geo: dict[str, list[tuple[str, float]]] = {}
    for flat_s, v in vals.items():
        try:
            flat = int(flat_s)
        except Exception:
            continue
        if v is None:
            continue
        g = (flat // time_size) % geo_size
        t = flat % time_size
        gc = idx_to_geo.get(g)
        tc = idx_to_time.get(t)
        if not gc or not tc:
            continue
        try:
            val = float(v)
        except Exception:
            continue
        per_geo.setdefault(gc, []).append((tc, val))

    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    for gc, series in per_geo.items():
        series.sort()  # by time ascending
        for i, (tc, v) in enumerate(series):
            mom = ""
            if i > 0 and series[i - 1][1]:
                prev = series[i - 1][1]
                mom = f"{100.0 * (v - prev) / prev:.2f}"
            yoy = ""
            # Find t-12
            if i >= 12 and series[i - 12][1]:
                prev_y = series[i - 12][1]
                yoy = f"{100.0 * (v - prev_y) / prev_y:.2f}"
            rows.append({
                "geo": gc,
                "geo_label": geo_lbl.get(gc, gc),
                "period": tc,
                "index_2021": f"{v:.2f}",
                "mom_pct": mom,
                "yoy_pct": yoy,
                "captured_at": now_iso,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"eu_indpro: empty, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["geo"], r["period"]))
    fieldnames = ["geo", "geo_label", "period", "index_2021",
                  "mom_pct", "yoy_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest reading per EU27 + DE + top movers.
    bits: list[str] = []
    for gc in ("EU27_2020", "DE", "FR", "IT"):
        recs = [r for r in rows if r["geo"] == gc]
        if recs:
            last = recs[-1]
            yoy = last["yoy_pct"] or "n/a"
            bits.append(f"{gc}={last['index_2021']} (YoY {yoy}%)")
    print(f"eu_indpro: {len(rows)} rows | {' '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
