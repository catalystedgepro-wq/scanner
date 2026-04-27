#!/usr/bin/env python3
"""build_nyfed_rates.py — NY Fed reference rates (SOFR / EFFR / OBFR).

Daily reference rates published by the Federal Reserve Bank of
New York. SOFR is the successor to LIBOR for USD floating-rate
contracts; EFFR tracks fed-funds tone inside the target corridor;
TGCR/BGCR are Treasury/broad GC repo benchmarks.

Series tracked (last 30 obs):
- SOFR   Secured Overnight Financing Rate (master USD benchmark)
- SOFRAI SOFR Averages & Index (30d / 90d / 180d compound)
- EFFR   Effective Federal Funds Rate (fed funds mid)
- OBFR   Overnight Bank Funding Rate (broad unsecured)
- TGCR   Tri-Party General Collateral Rate (Treasury repo)
- BGCR   Broad General Collateral Rate (Treasury + agency repo)

Signal for trading:
- SOFR-EFFR spread widening (>5bps persistent) = funding-market
  stress / repo fails. Historically correlates with SPX drawdown
  windows. Fade risk-parity (e.g., NTSX), bid short-vol hedges.
- SOFR percentile_99 > target_upper = month/quarter-end funding
  squeeze; softens BAC, JPM, GS prime-brokerage book PnL.
- SOFR volume < $2.5T = collateral/treasury-supply tightness; bid
  TLT (duration) on flight-to-quality.
- EFFR at target_from = IOER drift; watch Fed statement for RRP
  adjustment risk (signals small-cap/credit unwind).

Source: markets.newyorkfed.org/api/rates (no key).

Output: nyfed_rates.csv
Columns: rate_type, date, percent_rate, percentile_1, percentile_99,
         volume_bn, target_lower, target_upper, spread_vs_target_mid,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nyfed_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://markets.newyorkfed.org/api/rates"


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"nyfed_rates {url}: {e}")
        return {}


def main() -> None:
    rows: list[dict] = []
    # Per-rate endpoint returns last-N history; /all/ only has /latest/.
    endpoints = [
        (f"{BASE}/unsecured/effr/last/30.json"),
        (f"{BASE}/unsecured/obfr/last/30.json"),
        (f"{BASE}/secured/sofr/last/30.json"),
        (f"{BASE}/secured/sofrai/last/30.json"),
        (f"{BASE}/secured/tgcr/last/30.json"),
        (f"{BASE}/secured/bgcr/last/30.json"),
    ]
    merged: list[dict] = []
    for ep in endpoints:
        d = _fetch(ep)
        merged.extend(d.get("refRates", []) or [])

    for r in merged:
        rtype = r.get("type") or ""
        date = r.get("effectiveDate") or ""
        if not rtype or not date:
            continue
        # SOFRAI rows carry average30/90/180 + index, not percentRate.
        if rtype == "SOFRAI":
            pct = r.get("average30day")
            p01 = r.get("average90day")
            p99 = r.get("average180day")
            vol = r.get("index")
            tl = None
            tu = None
        else:
            pct = r.get("percentRate")
            p01 = r.get("percentPercentile1")
            p99 = r.get("percentPercentile99")
            vol = r.get("volumeInBillions")
            tl = r.get("targetRateFrom")
            tu = r.get("targetRateTo")
        if pct is None:
            continue
        if tl is not None and tu is not None:
            tgt_mid = (float(tl) + float(tu)) / 2
            spread = float(pct) - tgt_mid
        else:
            spread = None

        def _fmt(x, places: int = 4) -> str:
            if x is None:
                return ""
            try:
                return f"{float(x):.{places}f}"
            except Exception:
                return ""

        rows.append({
            "rate_type": rtype,
            "date": date,
            "percent_rate": _fmt(pct),
            "percentile_1": _fmt(p01),
            "percentile_99": _fmt(p99),
            "volume_bn": _fmt(vol, 2),
            "target_lower": _fmt(tl, 2),
            "target_upper": _fmt(tu, 2),
            "spread_vs_target_mid": (f"{spread:+.4f}"
                                     if spread is not None else ""),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nyfed_rates: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    rows.sort(key=lambda r: (r["rate_type"], r["date"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["rate_type", "date", "percent_rate", "percentile_1",
                  "percentile_99", "volume_bn", "target_lower",
                  "target_upper", "spread_vs_target_mid", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: latest SOFR + EFFR.
    def _latest(t: str) -> dict | None:
        xs = [r for r in rows if r["rate_type"] == t]
        return xs[-1] if xs else None

    sofr = _latest("SOFR")
    effr = _latest("EFFR")
    sofr_s = (f"SOFR {sofr['date']}={sofr['percent_rate']}%"
              if sofr else "")
    effr_s = (f"EFFR {effr['date']}={effr['percent_rate']}% "
              f"({effr['spread_vs_target_mid']}vs mid)"
              if effr else "")
    print(f"nyfed_rates: {len(rows)} rows | {sofr_s} | {effr_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
