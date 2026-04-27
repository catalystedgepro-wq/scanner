#!/usr/bin/env python3
"""build_crypto_funding.py — Perpetual futures funding + OI snapshot.

Funding rates on perpetual-swap crypto futures reveal levered
positioning skew. Positive funding = longs paying shorts (bullish
crowd); negative funding = shorts paying longs (bearish crowd or
squeeze setup). Open interest growth + price divergence signals
forced-liquidation risk.

Sources (all no-key public endpoints):
- OKX       /api/v5/public/funding-rate  (8h current rate)
- Kraken    /derivatives/api/v3/tickers   (mark, 24h vol, OI)
- Bitfinex  /v2/tickers                   (spot price + vol)

Symbols tracked: BTC, ETH, SOL, BNB, XRP, DOGE, AVAX, LINK, LTC,
ADA, MATIC, DOT.

Signal for trading:
- BTC funding > +0.05% (8h) sustained + price stalling = long
  squeeze setup; fade COIN/MSTR/MARA; bid BITI (inverse BTC).
- BTC funding < -0.03% with price rising = short squeeze; bid
  COIN/MSTR/MARA for 1-3 day burst.
- OI +15% week while funding neutral = stealth accumulation; bid
  miners MARA/RIOT/CLSK on breakout.
- OI down -20% after funding spike = delevering complete; low-risk
  entry for BITO/IBIT.

Output: crypto_funding.csv
Columns: exchange, symbol, price_usd, funding_rate_pct,
         funding_annualized_pct, open_interest_usd, vol_24h_usd,
         next_funding_time, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_funding.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

OKX_SYMS = [
    "BTC-USD-SWAP", "ETH-USD-SWAP", "SOL-USD-SWAP",
    "BNB-USD-SWAP", "XRP-USD-SWAP", "DOGE-USD-SWAP",
    "AVAX-USD-SWAP", "LINK-USD-SWAP", "LTC-USD-SWAP",
    "ADA-USD-SWAP", "MATIC-USD-SWAP", "DOT-USD-SWAP",
]
OKX_URL = "https://www.okx.com/api/v5/public/funding-rate?instId={}"

KRAKEN_URL = "https://futures.kraken.com/derivatives/api/v3/tickers"
KRAKEN_WANT = {
    "PF_XBTUSD": "BTC", "PF_ETHUSD": "ETH", "PF_SOLUSD": "SOL",
    "PF_XRPUSD": "XRP", "PF_DOGEUSD": "DOGE", "PF_AVAXUSD": "AVAX",
    "PF_LINKUSD": "LINK", "PF_LTCUSD": "LTC", "PF_ADAUSD": "ADA",
    "PF_MATICUSD": "MATIC", "PF_DOTUSD": "DOT",
}

BITFINEX_URL = ("https://api-pub.bitfinex.com/v2/tickers"
                "?symbols=tBTCUSD,tETHUSD,tSOLUSD,tXRPUSD,tDOGE:USD,"
                "tAVAX:USD,tLINK:USD,tLTCUSD,tADAUSD,tMATIC:USD,"
                "tDOTUSD")


def _fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"crypto_funding {url[:60]}: {e}")
        return None


def _sym_from_okx(instid: str) -> str:
    # "BTC-USD-SWAP" -> "BTC"
    return instid.split("-", 1)[0]


def _ms_to_iso(ms: str | int) -> str:
    try:
        ts = int(ms)
    except Exception:
        return ""
    if ts <= 0:
        return ""
    return (dt.datetime.fromtimestamp(ts / 1000, tz=dt.timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z"))


def fetch_okx() -> list[dict]:
    rows: list[dict] = []
    for inst in OKX_SYMS:
        d = _fetch(OKX_URL.format(inst))
        if not d or d.get("code") != "0":
            continue
        data = d.get("data") or []
        if not data:
            continue
        r = data[0]
        try:
            fr = float(r.get("fundingRate") or 0)
        except ValueError:
            continue
        # OKX funding is per 8h cycle => 3 cycles/day, 1095/year.
        rows.append({
            "exchange": "OKX",
            "symbol": _sym_from_okx(inst),
            "price_usd": "",
            "funding_rate_pct": f"{fr * 100:.5f}",
            "funding_annualized_pct": f"{fr * 100 * 3 * 365:.2f}",
            "open_interest_usd": "",
            "vol_24h_usd": "",
            "next_funding_time": _ms_to_iso(r.get("nextFundingTime")
                                            or 0),
        })
    return rows


def fetch_kraken() -> list[dict]:
    d = _fetch(KRAKEN_URL)
    if not d or d.get("result") != "success":
        return []
    rows: list[dict] = []
    for t in d.get("tickers", []) or []:
        sym = t.get("symbol") or ""
        if sym not in KRAKEN_WANT:
            continue
        try:
            mp = float(t.get("markPrice") or 0)
            oi = float(t.get("openInterest") or 0)
            vol = float(t.get("volumeQuote") or 0)
            fr = t.get("fundingRate")
            fr_pct = (f"{float(fr) * 100:.5f}"
                      if fr not in (None, "") else "")
            fr_ann = (f"{float(fr) * 100 * 24 * 365:.2f}"
                      if fr not in (None, "") else "")
        except ValueError:
            continue
        # Kraken PF is 1h funding -> 24 cycles/day -> 8760/year.
        rows.append({
            "exchange": "Kraken",
            "symbol": KRAKEN_WANT[sym],
            "price_usd": f"{mp:.4f}",
            "funding_rate_pct": fr_pct,
            "funding_annualized_pct": fr_ann,
            "open_interest_usd": f"{oi * mp:.0f}",
            "vol_24h_usd": f"{vol:.0f}",
            "next_funding_time": "",
        })
    return rows


def fetch_bitfinex() -> list[dict]:
    d = _fetch(BITFINEX_URL)
    if not isinstance(d, list):
        return []
    rows: list[dict] = []
    for t in d:
        if not isinstance(t, list) or len(t) < 11:
            continue
        sym_raw = t[0]
        # tBTCUSD -> BTC; tDOGE:USD -> DOGE.
        if not isinstance(sym_raw, str) or not sym_raw.startswith("t"):
            continue
        bare = sym_raw[1:].replace(":USD", "").replace("USD", "")
        if not bare:
            continue
        try:
            price = float(t[7]) if t[7] is not None else 0.0
            vol = float(t[8]) if t[8] is not None else 0.0
        except (ValueError, TypeError):
            continue
        rows.append({
            "exchange": "Bitfinex",
            "symbol": bare,
            "price_usd": f"{price:.4f}",
            "funding_rate_pct": "",
            "funding_annualized_pct": "",
            "open_interest_usd": "",
            "vol_24h_usd": f"{vol * price:.0f}",
            "next_funding_time": "",
        })
    return rows


def main() -> None:
    rows: list[dict] = []
    rows.extend(fetch_okx())
    rows.extend(fetch_kraken())
    rows.extend(fetch_bitfinex())

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"crypto_funding: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["symbol"], r["exchange"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["exchange", "symbol", "price_usd",
                  "funding_rate_pct", "funding_annualized_pct",
                  "open_interest_usd", "vol_24h_usd",
                  "next_funding_time", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary: OKX BTC + ETH funding + Kraken BTC OI.
    okx_btc = next((r for r in rows if r["exchange"] == "OKX"
                    and r["symbol"] == "BTC"), None)
    okx_eth = next((r for r in rows if r["exchange"] == "OKX"
                    and r["symbol"] == "ETH"), None)
    kraken_btc = next((r for r in rows if r["exchange"] == "Kraken"
                       and r["symbol"] == "BTC"), None)
    b_s = (f"OKX BTC fund={okx_btc['funding_rate_pct']}% "
           f"(ann {okx_btc['funding_annualized_pct']}%)"
           if okx_btc else "")
    e_s = (f"OKX ETH fund={okx_eth['funding_rate_pct']}%"
           if okx_eth else "")
    k_s = (f"Kraken BTC OI=${kraken_btc['open_interest_usd']}"
           if kraken_btc else "")
    print(f"crypto_funding: {len(rows)} rows | {b_s} | {e_s} | {k_s} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
