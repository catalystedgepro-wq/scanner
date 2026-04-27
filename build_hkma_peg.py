#!/usr/bin/env python3
"""build_hkma_peg.py — HKD peg stress + Hong Kong monetary tape.

The Hong Kong dollar trades in a narrow 7.75-7.85 band pegged to USD
via the Linked Exchange Rate System (LERS).  Stress on the peg is a
high-signal global macro alarm:
- HKD at weak-side (7.85) convertibility → capital outflow / China risk
- HIBOR spike → liquidity squeeze (2022, 2023 precedent)
- Aggregate balance collapse → HKMA intervention
- TWI move → relative-value shift in Asia

Fields captured:
- cu_weakside / cu_strongside (peg band: 7.85 / 7.75)
- disc_win_base_rate (HKMA base rate, tracks Fed)
- hibor_overnight, hibor_fixing_1m (interbank stress)
- twi (HKD trade-weighted index)
- closing_balance (aggregate liquidity in HKD bn)

Readthrough: China/HK ADRs (BABA, JD, PDD, BIDU, NIO, HSBC, PCG,
casinos WYNN/LVS), US financials with HK exposure (C, MS, GS),
Asian EM pairs.

Source: api.hkma.gov.hk public API
Output: hkma_peg.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hkma_peg.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = ("https://api.hkma.gov.hk/public/market-data-and-statistics/"
       "daily-monetary-statistics/daily-figures-interbank-liquidity"
       "?pagesize=60")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8",
                                                 errors="ignore"))
    except Exception as e:
        print(f"hkma_peg: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"hkma_peg: keeping {OUT_CSV.name}")
        return

    if not (isinstance(payload, dict) and
            payload.get("header", {}).get("success")):
        return
    records = payload.get("result", {}).get("records", [])
    if not records:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        try:
            weak = float(rec.get("cu_weakside") or 0) or 7.85
            strong = float(rec.get("cu_strongside") or 0) or 7.75
        except (TypeError, ValueError):
            weak, strong = 7.85, 7.75

        # Compute peg-stress proxy: HIBOR O/N vs base rate.
        base = rec.get("disc_win_base_rate")
        hibor_on = rec.get("hibor_overnight")
        try:
            spread = (float(hibor_on) - float(base)
                      if hibor_on is not None and base is not None
                      else None)
        except (TypeError, ValueError):
            spread = None

        rows.append({
            "date": rec.get("end_of_date", ""),
            "peg_weakside": f"{weak:.4f}",
            "peg_strongside": f"{strong:.4f}",
            "base_rate": str(base) if base is not None else "",
            "hibor_on": str(hibor_on) if hibor_on is not None else "",
            "hibor_1m": str(rec.get("hibor_fixing_1m", "") or ""),
            "on_vs_base_bps": (f"{spread * 100:.1f}"
                               if spread is not None else ""),
            "twi": str(rec.get("twi", "") or ""),
            "agg_balance": str(rec.get("closing_balance", "") or ""),
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"hkma_peg: empty, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date", "peg_weakside", "peg_strongside",
                  "base_rate", "hibor_on", "hibor_1m",
                  "on_vs_base_bps", "twi", "agg_balance",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    print(f"hkma_peg: {len(rows)} days | latest={latest['date']} "
          f"hibor_on={latest['hibor_on']} "
          f"spread={latest['on_vs_base_bps']}bps "
          f"twi={latest['twi']} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
