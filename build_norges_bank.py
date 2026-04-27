#!/usr/bin/env python3
"""build_norges_bank.py — Norges Bank (Norway) FX + policy rate.

SDMX-JSON API publishes daily FX observations and key rate.

Economic readthrough:
- Norway is sovereign-wealth superpower (oil-fund 18 trn NOK, #1 global SWF).
- NOK is oil-linked (brent beta); petro-krone weakens when oil sells off.
- Equinor (EQNR) / Aker BP / Vaar Energi feed; Norsk Hydro for aluminum.
- Key rate = Scandi benchmark; Riksbank + ECB cross-reference.
- NOK/SEK = Nordic carry; NOK/USD tracks brent via 30-day correlation.

Sources:
- FX:   data.norges-bank.no/api/data/EXR/B.{CUR}.NOK.SP
- Rate: data.norges-bank.no/api/data/IR/B.KPRA.SD.R

Output: norges_bank.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "norges_bank.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FX_PAIRS = ["USD", "EUR", "GBP", "JPY", "CHF", "SEK", "DKK", "CNY"]


def _fetch(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _parse_sdmx(d: dict, metric: str, scale: int = 1) -> list[dict]:
    """Flatten SDMX-JSON dataset to list of {date, value} rows.

    Norges Bank JPY is quoted per 100 JPY → scale=100 divides out to NOK/1JPY.
    """
    out: list[dict] = []
    data = d.get("data") or {}
    ds_list = data.get("dataSets") or []
    if not ds_list:
        return out
    struct = data.get("structure", {})
    obs_dims = struct.get("dimensions", {}).get("observation", [])
    if not obs_dims:
        return out
    time_values = [x.get("id") for x in obs_dims[0].get("values", [])]
    series = ds_list[0].get("series", {})
    for _, sdef in series.items():
        obs = sdef.get("observations", {}) or {}
        for idx_str, vals in obs.items():
            try:
                idx = int(idx_str.split(":")[0])
            except ValueError:
                continue
            if idx >= len(time_values):
                continue
            try:
                val = float(vals[0]) if vals and vals[0] is not None else None
            except (TypeError, ValueError):
                val = None
            if val is None:
                continue
            if scale != 1:
                val = val / scale
            out.append({
                "metric": metric,
                "date": time_values[idx],
                "value": round(val, 6),
            })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []

    # FX pairs — 60 days each
    for cur in FX_PAIRS:
        url = (f"https://data.norges-bank.no/api/data/EXR/"
               f"B.{cur}.NOK.SP?format=sdmx-json&lastNObservations=60")
        try:
            d = _fetch(url)
        except Exception as e:
            print(f"norges_bank: {cur}/NOK fetch failed: {e}")
            continue
        # Norges Bank quotes JPY/CNY/SEK/DKK per 100 foreign currency.
        scale = 100 if cur in {"JPY", "CNY", "SEK", "DKK"} else 1
        metric = f"{cur}NOK"
        rows.extend(_parse_sdmx(d, metric, scale))
        time.sleep(0.8)

    # Key policy rate (daily effective)
    try:
        d = _fetch("https://data.norges-bank.no/api/data/IR/"
                   "B.KPRA.SD.R?format=sdmx-json&lastNObservations=90")
        rows.extend(_parse_sdmx(d, "key_rate"))
    except Exception as e:
        print(f"norges_bank: key_rate fetch failed: {e}")

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"norges_bank: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["metric"], r["date"]), reverse=True)

    fieldnames = ["metric", "date", "value", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Latest snapshot per metric
    latest: dict[str, tuple[str, float]] = {}
    for r in rows:
        m = r["metric"]
        if m not in latest:
            latest[m] = (r["date"], r["value"])
    hl_keys = ["USDNOK", "EURNOK", "GBPNOK", "SEKNOK", "key_rate"]
    hb = " ".join(
        f"{k}={latest[k][1]}" for k in hl_keys if k in latest)
    print(f"norges_bank: {len(rows)} rows across {len(latest)} metrics | "
          f"{hb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
