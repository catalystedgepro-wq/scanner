#!/usr/bin/env python3
"""build_cointelegraph.py — Cointelegraph News RSS firehose.

Source: cointelegraph.com/rss (RSS 2.0, ~30-item rolling, hourly, free,
no key, CDATA-wrapped). Distinct from all existing numeric/on-chain
crypto spokes (blockchair_onchain, coinbase_spot, coingecko_derivatives,
coingecko_top, crypto_correlation, crypto_defi, crypto_exchanges,
crypto_fear_greed, crypto_funding, crypto_global, crypto_onchain,
crypto_stablecoins, crypto_treasury, defillama_dexs, defillama_tvl,
sec_crypto, stablecoins) — this is the editorial-narrative layer that
telegraphs 24-48h institutional positioning around BTC/ETH/stablecoin
ETF flows, SEC/CFTC/FCA/MAS regulatory tape, exchange solvency signals,
DeFi exploit events, and mining-equity catalysts (MARA/RIOT/HUT/CLSK/
HIVE/BITF/CIFR/CORZ/WULF/IREN).

Taxonomy (priority-ordered, first-match-wins):
  regulation / etf / hack / exchange / stablecoin / defi / bitcoin /
  ethereum / nft / corporate / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request
from email.utils import parsedate_to_datetime

FEED = "https://cointelegraph.com/rss"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "cointelegraph.csv"
FIELDS = ["filed_utc", "kind", "title", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("regulation", re.compile(r"\b(SEC|Atkins|Gensler|CFTC|OCC|FinCEN|OFAC|Treasury|IRS|DOJ|FBI|FATF|FCA|MAS|BaFin|ASIC|MiCA|Travel Rule|enforcement|lawsuit|subpoena|indict|charged|fine|settlement|penalty|Senate Banking|House Financial Services|Warren|Lummis|regulator|rulemaking|guidance|no[- ]action letter)\b", re.I)),
    ("etf", re.compile(r"\b(ETF|spot ETF|futures ETF|Bitcoin ETF|Ether ETF|Ethereum ETF|BlackRock|iShares|Fidelity|Grayscale|GBTC|IBIT|FBTC|ARKB|BITB|BITO|ETHE|ETHA|spot approval|19b-4|S-1|in[- ]kind|creation unit|NAV premium|NAV discount|outflow|inflow)\b", re.I)),
    ("hack", re.compile(r"\b(hack|hacker|hacked|exploit|exploiter|drained|drain|stolen|theft|rug pull|rugged|phishing|scam|bridge exploit|flash loan|reentrancy|smart contract vulnerability|bug bounty|audit find|whitehat|blackhat|north korean|Lazarus|DPRK)\b", re.I)),
    ("exchange", re.compile(r"\b(Binance|Coinbase|Kraken|OKX|Bybit|Gemini|Bitfinex|Huobi|KuCoin|Gate\.io|Bitstamp|Crypto\.com|FTX|Mt\.? Gox|exchange outflow|exchange inflow|order book|custody|prime brokerage|CEX|centralized exchange|derivatives exchange|CME|CBOE)\b", re.I)),
    ("stablecoin", re.compile(r"\b(stablecoin|USDT|Tether|USDC|Circle|PYUSD|PayPal|DAI|MakerDAO|FDUSD|First Digital|TUSD|USDP|Paxos|FRAX|LUSD|crvUSD|GHO|depeg|peg|reserve attestation|CUSIP holding|T-bill backing)\b", re.I)),
    ("defi", re.compile(r"\b(DeFi|DEX|Uniswap|Curve|Aave|Compound|MakerDAO|Lido|Rocket Pool|EigenLayer|Pendle|GMX|dYdX|Jupiter|Raydium|Orca|TVL|total value locked|yield farming|liquid staking|restaking|AVS|LST|LRT|LP token|impermanent loss|governance token)\b", re.I)),
    ("bitcoin", re.compile(r"\b(Bitcoin|BTC|Satoshi|halving|difficulty adjustment|hash rate|hashrate|miner|mining|Ordinals|Runes|BRC-20|Lightning Network|Taproot|mempool|MicroStrategy|MSTR|Saylor|El Salvador|legal tender|treasury reserve asset|BTC[- ]denominated)\b", re.I)),
    ("ethereum", re.compile(r"\b(Ethereum|Ether\b|ETH\b|Vitalik|Buterin|Pectra|Dencun|Cancun|Shanghai|merge|EIP[- ]?\d|layer 2|layer[- ]2|L2|rollup|Optimism|Arbitrum|Base|zkSync|Starknet|Polygon|blob|proto[- ]danksharding|validator|staking|beacon chain)\b", re.I)),
    ("nft", re.compile(r"\b(NFT|non[- ]fungible|OpenSea|Blur|Magic Eden|Pudgy Penguins|BAYC|Bored Ape|CryptoPunks|Azuki|Moonbirds|Art Blocks|digital collectible|PFP|ordinal inscription)\b", re.I)),
    ("corporate", re.compile(r"\b(MSTR|MicroStrategy|Block Inc|Square|SQ\b|Coinbase Global|COIN\b|Robinhood|HOOD|MARA|Marathon|RIOT|Riot Platforms|HUT|CLSK|CleanSpark|HIVE|BITF|CIFR|Cipher|CORZ|Core Scientific|WULF|IREN|Iris Energy|BitGo|Galaxy Digital|GLXY|treasury holding|corporate buyer|institutional)\b", re.I)),
)


def _clean(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[|\]\]>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _parse_pub(raw: str) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip())
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify(title: str, summary: str) -> str:
    hay = f"{title} {summary}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    rows: list[dict] = []
    for block in re.findall(r"<item>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)

        title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        filed = _parse_pub(_clean(date_m.group(1))) if date_m else None
        summary = _clean(desc_m.group(1)) if desc_m else ""

        if not title:
            continue
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append(
            {
                "filed_utc": filed,
                "kind": _classify(title, summary),
                "title": title[:240],
                "link": link,
                "summary": summary[:400],
            }
        )
    rows.sort(key=lambda r: r["filed_utc"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[cointelegraph] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[cointelegraph] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[cointelegraph] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[cointelegraph] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
