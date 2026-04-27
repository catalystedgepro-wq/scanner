#!/usr/bin/env python3
"""build_ofr_fsi.py — OFR Financial Stress Index (daily, since 2000).

Office of Financial Research's flagship stress index: daily composite
of credit, equity valuation, safe-asset flight, funding, and
volatility — broken out across US, OAE, and EM. One of the cleanest
macro-risk regime signals available (free, government-backed, daily).

Signal:
- OFR FSI > +1.0 = stress regime → defensive rotation (staples, gold,
  treasuries); risk-off squeeze targets (TLT, GLD, XLP, VIX calls)
- OFR FSI < -1.0 = complacency → risk-on extension; short-vol, credit
  carry trades favored (XLF, HYG, LQD, KBE)
- Component divergence: Funding stress + low Volatility = hidden
  pipeline stress (e.g., repo market cracks masked by equity calm)
- United States vs EM spread: signal for US-over-EM rotation when
  EM stress spikes
- 5-day + 20-day Z-score = regime change detector (pattern used in
  the 2008, 2020, 2023 SVB, and 2024 carry unwind events)

Drives:
- Equity beta (SPY, QQQ) via regime switch
- Credit (HYG, LQD, BKLN)
- Treasury ETFs (TLT, IEF, SHY)
- Volatility (VXX, UVXY, VIX futures)
- Gold (GLD, IAU) as defensive
- Banks (XLF, KRE) via funding-stress proxy

Source: financialresearch.gov/financial-stress-index/data/fsi.csv
Output: ofr_fsi.csv
Columns: date, fsi, credit, equity_val, safe_assets, funding,
         volatility, us, oae, em, z5, z20, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import statistics
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ofr_fsi.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
KEEP_DAYS = 260  # ~1 trading year


def _f(v: str) -> float | None:
    if v in (None, "", "NA"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _z(series: list[float], n: int) -> float | None:
    if len(series) < n or n < 2:
        return None
    window = series[-n:]
    mu = statistics.fmean(window)
    sigma = statistics.pstdev(window)
    if sigma == 0:
        return None
    return (window[-1] - mu) / sigma


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"ofr_fsi: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ofr_fsi: keeping existing {OUT_CSV.name}")
        return

    reader = list(csv.DictReader(StringIO(text)))
    if not reader:
        return

    # Keep last KEEP_DAYS only.
    reader = reader[-KEEP_DAYS:]

    # Build z-score over growing window.
    fsi_series: list[float] = []
    rows: list[dict] = []
    for rec in reader:
        date = rec.get("Date", "")
        fsi = _f(rec.get("OFR FSI"))
        if fsi is None:
            continue
        fsi_series.append(fsi)
        z5 = _z(fsi_series, 5)
        z20 = _z(fsi_series, 20)
        rows.append({
            "date": date,
            "fsi": f"{fsi:+.3f}",
            "credit": (f"{_f(rec.get('Credit')):+.3f}"
                       if _f(rec.get("Credit")) is not None else ""),
            "equity_val": (f"{_f(rec.get('Equity valuation')):+.3f}"
                           if _f(rec.get("Equity valuation")) is not None
                           else ""),
            "safe_assets": (f"{_f(rec.get('Safe assets')):+.3f}"
                            if _f(rec.get("Safe assets")) is not None
                            else ""),
            "funding": (f"{_f(rec.get('Funding')):+.3f}"
                        if _f(rec.get("Funding")) is not None else ""),
            "volatility": (f"{_f(rec.get('Volatility')):+.3f}"
                           if _f(rec.get("Volatility")) is not None else ""),
            "us": (f"{_f(rec.get('United States')):+.3f}"
                   if _f(rec.get("United States")) is not None else ""),
            "oae": (f"{_f(rec.get('Other advanced economies')):+.3f}"
                    if _f(rec.get("Other advanced economies")) is not None
                    else ""),
            "em": (f"{_f(rec.get('Emerging markets')):+.3f}"
                   if _f(rec.get("Emerging markets")) is not None else ""),
            "z5": f"{z5:+.2f}" if z5 is not None else "",
            "z20": f"{z20:+.2f}" if z20 is not None else "",
        })

    if not rows:
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["date", "fsi", "credit", "equity_val", "safe_assets",
                  "funding", "volatility", "us", "oae", "em", "z5", "z20",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    delta = ""
    if prev:
        try:
            delta = f"{float(last['fsi']) - float(prev['fsi']):+.3f}"
        except ValueError:
            pass
    regime = "calm"
    try:
        f_ = float(last["fsi"])
        if f_ > 1:
            regime = "STRESS"
        elif f_ < -1:
            regime = "complacent"
    except ValueError:
        pass
    print(f"ofr_fsi: {len(rows)} rows | {last['date']} FSI={last['fsi']} "
          f"Δ={delta} funding={last['funding']} vol={last['volatility']} "
          f"z20={last['z20']} regime={regime} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
