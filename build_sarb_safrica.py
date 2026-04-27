#!/usr/bin/env python3
"""build_sarb_safrica.py — SARB (South Africa) macro snapshot.

SARB HomePageRates JSON endpoint returns a compact list of headline
economic indicators: CPI, PPI, SARB repo rate, prime rate, USDZAR,
current-account, bond yields, etc.

Economic readthrough:
- ZAR is a commodity-currency bellwether (platinum, gold, coal).
- High beta to global risk-off and China growth signal.
- SA-ADRs: GFI (Gold Fields), AU (AngloGold), HMY (Harmony),
  SBSW (Sibanye), IMPUY (Impala).
- Repo rate at 6.75%; CPI target band 3-6% — SARB just above ceiling.
- Twin deficit + weak growth = ZAR carry unwind risk on global VIX
  spike.

Source: https://custom.resbank.co.za/SarbWebApi/WebIndicators/HomePageRates
Output: sarb_safrica.csv

One-shot daily snapshot (no historical deep archive from this API).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sarb_safrica.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://custom.resbank.co.za/SarbWebApi/WebIndicators/"
       "HomePageRates")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            items = json.loads(
                r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"sarb_safrica: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sarb_safrica: keeping {OUT_CSV.name}")
        return

    if not isinstance(items, list) or not items:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            value = float(it.get("Value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        rows.append({
            "name": (it.get("Name", "") or "")[:40],
            "section": it.get("SectionName", "") or "",
            "code": it.get("TimeseriesCode", "") or "",
            "date": (it.get("Date", "") or "")[:10],
            "value": value,
            "up_down": it.get("UpDown", 0),
            "captured_at": now_iso,
        })

    if not rows:
        return

    rows.sort(key=lambda r: (r["section"], r["name"]))
    fieldnames = ["name", "section", "code", "date", "value",
                  "up_down", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_section: dict[str, int] = {}
    for r in rows:
        k = r["section"] or "?"
        by_section[k] = by_section.get(k, 0) + 1
    headline = {}
    for r in rows:
        code = r["code"].upper()
        if "MMRD" in code and "policy" not in headline:
            headline["policy"] = r["value"]
        elif "CPI1" in code and "cpi" not in headline:
            headline["cpi"] = r["value"]
        elif "PPI1" in code and "ppi" not in headline:
            headline["ppi"] = r["value"]
        elif r["name"].upper().startswith("USD") and "usdzar" not in \
                headline:
            headline["usdzar"] = r["value"]
    hb = " ".join(f"{k}={v}" for k, v in headline.items())
    sb = " ".join(f"{k[:8]}={v}" for k, v in sorted(
        by_section.items(), key=lambda x: -x[1])[:4])
    print(f"sarb_safrica: {len(rows)} indicators | {hb} | "
          f"sections={sb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
