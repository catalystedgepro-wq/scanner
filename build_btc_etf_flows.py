#!/usr/bin/env python3
"""build_btc_etf_flows.py — daily BTC spot ETF dollar flow proxy.

The 11 spot Bitcoin ETFs (IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL,
BTCW, GBTC, DEFI) collectively hold $50B+ AUM. Daily net flow into/out of
this complex is one of the strongest catalysts on the tape — drives BTC
spot, miner equities (RIOT, MARA, CLSK), Coinbase (COIN), and Bitcoin
treasury names (MSTR).

This spoke approximates daily net dollar flow per fund using Yahoo's chart
API (free, no auth):
    flow_proxy_usd = volume × close_price

That overstates absolute flow (it counts gross volume) but the *relative*
day-over-day delta and the ranking across funds are reliable. For absolute
net flows we'd need Farside or BitMEX research scrapes — not free.

Output: btc_etf_flows.csv
Columns:
    captured_at, ticker, name, close, volume, dollar_volume_usd,
    pct_change, vol_vs_20d, regime
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_btc_etf_flows.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
OUT = ROOT / "docs/btc_etf_flows.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

UA = "CatalystEdge/1.0"
TIMEOUT = 12

ETFS = [
    ("IBIT",  "iShares Bitcoin Trust"),
    ("FBTC",  "Fidelity Wise Origin Bitcoin"),
    ("BITB",  "Bitwise Bitcoin"),
    ("ARKB",  "ARK 21Shares Bitcoin"),
    ("BTCO",  "Invesco Galaxy Bitcoin"),
    ("EZBC",  "Franklin Bitcoin"),
    ("BRRR",  "Valkyrie Bitcoin"),
    ("HODL",  "VanEck Bitcoin"),
    ("BTCW",  "WisdomTree Bitcoin"),
    ("GBTC",  "Grayscale Bitcoin Trust"),
    ("DEFI",  "Hashdex Bitcoin"),
]


def fetch_chart(ticker: str) -> dict | None:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ticker)
        + "?range=1mo&interval=1d"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"  fetch fail {ticker}: {e}")
        return None


def regime_label(dollar_volume: float, avg20: float) -> str:
    if not avg20:
        return "unknown"
    r = dollar_volume / avg20
    if r >= 3.0:
        return "frenzy"
    if r >= 2.0:
        return "spike"
    if r >= 1.5:
        return "elevated"
    if r >= 0.7:
        return "normal"
    return "fade"


def main() -> int:
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    total_today = 0.0

    for ticker, name in ETFS:
        chart = fetch_chart(ticker)
        if not chart:
            continue
        result = (chart.get("chart") or {}).get("result") or []
        if not result:
            continue
        ind = (result[0].get("indicators") or {}).get("quote") or [{}]
        closes = ind[0].get("close") or []
        vols = ind[0].get("volume") or []
        if not closes or not vols:
            continue

        # Strip None
        closes = [c for c in closes if c is not None]
        vols = [v for v in vols if v is not None]
        if len(closes) < 2 or not vols:
            continue

        close = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else close
        pct = ((close - prev) / prev * 100.0) if prev else 0.0
        vol = vols[-1]
        dollar_vol = close * vol

        # 20-day average dollar volume
        n = min(20, len(closes), len(vols))
        avg20 = sum(c * v for c, v in zip(closes[-n:], vols[-n:])) / n if n else 0
        regime = regime_label(dollar_vol, avg20)

        total_today += dollar_vol
        rows.append({
            "captured_at": captured,
            "ticker": ticker,
            "name": name,
            "close": round(close, 2),
            "volume": int(vol),
            "dollar_volume_usd": round(dollar_vol, 0),
            "pct_change": round(pct, 2),
            "vol_vs_20d": round(dollar_vol / avg20, 2) if avg20 else 0,
            "regime": regime,
        })

    rows.sort(key=lambda r: r["dollar_volume_usd"], reverse=True)

    if rows:
        with OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    leader = rows[0]["ticker"] if rows else "?"
    frenzy_count = sum(1 for r in rows if r["regime"] in ("frenzy", "spike"))
    print(f"btc_etf_flows: {len(rows)} ETFs | "
          f"complex_today=${total_today/1e9:.2f}B | "
          f"leader={leader} | spikes={frenzy_count}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
