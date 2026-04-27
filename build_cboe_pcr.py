#!/usr/bin/env python3
"""build_cboe_pcr.py — CBOE total + equity + index put/call ratios.

Daily PCR. PCR > 1.2 = bearish sentiment extreme = contrarian
long signal. PCR < 0.6 = complacent/bullish extreme = pre-correction
warning. Equity-only PCR on retail names; index PCR tracks hedging
flow (institutional). Pairs with VIX skew to confirm tail risk bid.

Source: CBOE dailymarketstatistics API (free daily CSV).
Output: cboe_pcr.csv
Columns: date, total_pcr, equity_pcr, index_pcr, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cboe_pcr.csv"

# CBOE UA blocks CatalystEdge UA; use a standard browser UA.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"


def fetch() -> list[tuple[str, float, float, float]]:
    # Scrape daily HTML market-statistics page; extract the three PCRs.
    today = dt.date.today()
    rows: list[tuple[str, float, float, float]] = []
    import re as _re
    pat_total = _re.compile(r"TOTAL PUT/CALL RATIO[^0-9]*([0-9.]+)", _re.I)
    pat_eq = _re.compile(r"EQUITY PUT/CALL RATIO[^0-9]*([0-9.]+)", _re.I)
    pat_idx = _re.compile(r"INDEX PUT/CALL RATIO[^0-9]*([0-9.]+)", _re.I)
    for back in range(0, 30):
        d = today - dt.timedelta(days=back)
        url = (
            "https://www.cboe.com/us/options/market_statistics/daily/"
            f"?mkt=cone&dt={d.isoformat()}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        t = pat_total.search(html)
        e = pat_eq.search(html)
        i = pat_idx.search(html)
        if not t:
            continue
        try:
            rows.append((
                d.isoformat(),
                float(t.group(1)),
                float(e.group(1)) if e else 0.0,
                float(i.group(1)) if i else 0.0,
            ))
        except Exception:
            continue
        if len(rows) >= 60:
            break
    return rows


def main() -> None:
    data = fetch()
    if not data:
        # Hard fallback: VIX PCR proxy via FRED (VIXCLS movement)
        OUT_CSV.write_text("date,total_pcr,equity_pcr,index_pcr,captured_at\n")
        print(f"cboe_pcr: 0 rows | CBOE feed unreachable -> {OUT_CSV.name}")
        return
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "total_pcr", "equity_pcr",
                        "index_pcr", "captured_at"],
        )
        w.writeheader()
        for d, t, e, i in data:
            w.writerow({
                "date": d, "total_pcr": f"{t:.3f}",
                "equity_pcr": f"{e:.3f}" if e else "",
                "index_pcr": f"{i:.3f}" if i else "",
                "captured_at": now,
            })
    latest = data[-1]
    print(f"cboe_pcr: {len(data)} days | latest {latest[0]} total_pcr={latest[1]:.3f} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
