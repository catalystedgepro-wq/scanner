#!/usr/bin/env python3
"""build_crypto_global.py — CoinGecko global crypto market snapshot.

CoinGecko's /global endpoint gives aggregated crypto market state:
total market cap, 24h trading volume, BTC / ETH dominance %, and
number of active cryptocurrencies. Dominance ratios are a leading
risk-appetite gauge:

- BTC dominance rising while total mcap falling = flight to quality
  inside crypto (alts being abandoned); weakens SOL, AVAX, MATIC
  altcoin equity proxies.
- ETH dominance rising without BTC rising = DeFi rotation; bid COIN
  (exchange volume beneficiary), HOOD (retail altcoin flow).
- Total mcap breaking $3T threshold + BTC dom < 48% = retail
  euphoria peak; fade MARA, RIOT, MSTR on squeeze exhaustion.
- Stablecoin mcap flat while total mcap drops = no fresh fiat
  inflow; stealth liquidation warning.

Output (single snapshot row):
  total_market_cap_usd, total_volume_24h_usd, btc_dominance_pct,
  eth_dominance_pct, market_cap_change_24h_pct,
  active_cryptocurrencies, markets, upcoming_icos,
  ongoing_icos, ended_icos, captured_at

Source: api.coingecko.com/api/v3/global (public free tier, ~30 rpm).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "crypto_global.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.coingecko.com/api/v3/global"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"crypto_global: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"crypto_global: keeping existing {OUT_CSV.name}")
        return

    data = d.get("data") or {}
    if not data:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"crypto_global: empty payload, keeping existing "
                  f"{OUT_CSV.name}")
        return

    total_mcap = (data.get("total_market_cap") or {}).get("usd") or 0
    total_vol = (data.get("total_volume") or {}).get("usd") or 0
    mcap_pct = data.get("market_cap_percentage") or {}
    btc_dom = mcap_pct.get("btc") or 0
    eth_dom = mcap_pct.get("eth") or 0

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    row = {
        "total_market_cap_usd": f"{float(total_mcap):.0f}",
        "total_volume_24h_usd": f"{float(total_vol):.0f}",
        "btc_dominance_pct": f"{float(btc_dom):.2f}",
        "eth_dominance_pct": f"{float(eth_dom):.2f}",
        "market_cap_change_24h_pct": (
            f"{float(data.get('market_cap_change_percentage_24h_usd') or 0):.2f}"
        ),
        "active_cryptocurrencies": str(
            data.get("active_cryptocurrencies") or 0),
        "markets": str(data.get("markets") or 0),
        "upcoming_icos": str(data.get("upcoming_icos") or 0),
        "ongoing_icos": str(data.get("ongoing_icos") or 0),
        "ended_icos": str(data.get("ended_icos") or 0),
        "captured_at": now,
    }

    fieldnames = ["total_market_cap_usd", "total_volume_24h_usd",
                  "btc_dominance_pct", "eth_dominance_pct",
                  "market_cap_change_24h_pct",
                  "active_cryptocurrencies", "markets",
                  "upcoming_icos", "ongoing_icos", "ended_icos",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(row)

    print(f"crypto_global: mcap=${float(total_mcap) / 1e12:.2f}T "
          f"(24h {row['market_cap_change_24h_pct']}%) "
          f"BTC_dom={row['btc_dominance_pct']}% "
          f"ETH_dom={row['eth_dominance_pct']}% "
          f"vol=${float(total_vol) / 1e9:.0f}B -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
