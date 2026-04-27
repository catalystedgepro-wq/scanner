#!/usr/bin/env python3
"""build_ecb_fx.py — ECB Euro reference FX rates, 90-day history.

FX moves are a primary cross-border equity catalyst:
- **USD strength (EUR/USD falling)**: hurts US mega-cap multinational EPS
  (MSFT ~25% EU revenue, AAPL ~20%, PG, MCD, KO, PFE). DXY rally → long
  defensive US small-caps (IWM) vs large-cap. Also pressures EM equity
  (EEM, EWZ, EWW) and gold (GLD).
- **JPY weakness (EUR/JPY, USD/JPY rising)**: Japanese exporter tailwind
  (TM, SONY, NSANY ADRs). At extremes (USD/JPY > 160), BoJ intervention
  risk → sharp reversal. Also key carry-trade input; unwind = risk-off.
- **GBP strength (EUR/GBP falling)**: hurts UK exporters (BP, SHEL, HSBC
  via translation). Favors GBP-earning US MNCs (MMM, CAT).
- **CNY weakness (EUR/CNY, USD/CNY rising)**: deflation export to US
  (bad for US small-cap manufacturers, good for importers like WMT,
  COST). Chinese ADRs (BABA, JD) benefit from RMB-denominated earnings
  translated to weaker USD terms.
- **EM FX stress (TRY, BRL, MXN, ZAR devaluation > 5% in 30d)**:
  sovereign-debt pressure, short EEM/EWZ/EWW/TUR, long USD strength
  plays. Historical precedent: 2018 Turkey lira crisis = -40% EWZ in
  6 months via contagion.
- **KRW stress**: semi-supply chain risk (TSM, AVGO, MU) via Korea's
  role in memory + display production.

Trade uses:
- 30-day % change > 3% in EUR/USD → long EZU short SPY (or reverse)
- USD/JPY > 155: watch for BoJ intervention (buy USD/JPY puts via UUP)
- EM basket (BRL+MXN+ZAR) devaluing > 5%/30d: EEM short setup
- CHF strengthening > 2%/week: risk-off signal (long VIX, short small-
  cap beta)

Source: www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml
Free, no key, stdlib only, updates 16:00 CET weekdays (~3 PM UTC).

Output: ecb_fx.csv
Columns: date, currency, rate_eur, pct_1d, pct_30d, pct_90d, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ecb_fx.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"

# Focus list — high-beta crosses for equity trade setups. Filtering to
# these keeps the CSV tight and the signal focused.
KEEP = {
    "USD", "JPY", "GBP", "CAD", "CHF", "AUD", "NZD",
    "CNY", "HKD", "KRW", "INR", "SGD", "THB", "IDR",
    "MXN", "BRL", "TRY", "ZAR", "ILS",
}

NS = {
    "g": "http://www.gesmes.org/xml/2002-08-01",
    "e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref",
}


def fetch() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception as e:
        print(f"ecb_fx: {e}")
        return b""


def _pct(series: list[tuple[str, float]], idx: int, back: int) -> str:
    """% change for series[idx] vs series[idx-back]. Series is ordered
    newest-first, so idx-back is older. Returns '' if missing."""
    if idx + back >= len(series):
        return ""
    new = series[idx][1]
    old = series[idx + back][1]
    if old == 0:
        return ""
    return f"{((new - old) / old) * 100.0:+.2f}"


def main() -> None:
    raw = fetch()
    if not raw and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"ecb_fx: fetch failed, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"ecb_fx: XML parse error: {e}")
        return

    # By currency: list of (date, rate) newest-first.
    by_ccy: dict[str, list[tuple[str, float]]] = {}
    for day in root.findall(".//e:Cube[@time]", NS):
        date = day.get("time", "")
        for c in day.findall("./e:Cube", NS):
            code = c.get("currency", "")
            rate = c.get("rate", "")
            if code not in KEEP:
                continue
            try:
                by_ccy.setdefault(code, []).append((date, float(rate)))
            except ValueError:
                continue

    if not by_ccy and OUT_CSV.exists() and OUT_CSV.stat().st_size > 500:
        print(f"ecb_fx: parsed empty, keeping existing {OUT_CSV.name}")
        return

    # ECB XML is already newest-first per day block, but be explicit.
    for code in by_ccy:
        by_ccy[code].sort(key=lambda p: p[0], reverse=True)

    rows: list[dict] = []
    for code, series in by_ccy.items():
        for i, (date, rate) in enumerate(series):
            rows.append({
                "date": date,
                "currency": code,
                "rate_eur": f"{rate:.4f}",
                "pct_1d": _pct(series, i, 1),
                "pct_30d": _pct(series, i, 30),
                "pct_90d": _pct(series, i, 89),
            })

    # Sort: date desc, then currency
    rows.sort(key=lambda r: (r["date"], r["currency"]), reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "currency", "rate_eur", "pct_1d",
                        "pct_30d", "pct_90d", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)

    # Summary: latest-day snapshot of key crosses + 30-day extremes.
    latest_date = rows[0]["date"] if rows else "?"
    today = [r for r in rows if r["date"] == latest_date]

    def _fmt(code: str) -> str:
        r = next((x for x in today if x["currency"] == code), None)
        if not r:
            return f"{code}=?"
        return f"{code}={r['rate_eur']} ({r['pct_30d'] or '—'}%)"

    hdr = " | ".join(_fmt(c) for c in ("USD", "JPY", "GBP", "CNY", "MXN"))

    # 30-day movers (most extreme)
    movers = [r for r in today if r["pct_30d"]]
    movers.sort(key=lambda r: abs(float(r["pct_30d"])), reverse=True)
    top3 = ", ".join(
        f"{r['currency']} {r['pct_30d']}%" for r in movers[:3]
    )

    print(f"ecb_fx: {len(rows)} rows | {latest_date} | {hdr} | "
          f"top 30d movers: {top3} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
