#!/usr/bin/env python3
"""build_hnews_attention.py — Hacker News top-story tech attention tape.

Hacker News top stories = highest-signal early-warning for technical
interest shifts. Relevant to equity conviction:
- AI-story density → concentration rotation (NVDA, GOOGL, META, MSFT)
- Crypto-story mentions → speculative rotation (COIN, MSTR, MARA)
- Security breach / zero-day stories → PANW/CRWD/ZS/NET bid
- Layoff / company-struggle stories → ticker-specific drawdown
- Browser / OS release stories → GOOGL / AAPL / MSFT product cycle
- New-database / cloud stories → SNOW / MDB / DDOG / CFLT readthrough

Source: hacker-news.firebaseio.com/v0/topstories.json + /v0/item/{id}.json
Output: hnews_attention.csv

Enriches each story with per-ticker sentiment by scanning title + url
for well-known ticker keywords.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "hnews_attention.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://hacker-news.firebaseio.com/v0"
TOP_N = 80  # top-story slice to fetch

KEYWORD_TICKERS = {
    "openai": "MSFT", "chatgpt": "MSFT", "gpt-4": "MSFT", "gpt-5": "MSFT",
    "copilot": "MSFT", "azure": "MSFT", "microsoft": "MSFT",
    "github": "MSFT", "office 365": "MSFT",
    "anthropic": "",  # private
    "claude": "",
    "google": "GOOGL", "gemini": "GOOGL", "android": "GOOGL",
    "chrome": "GOOGL", "deepmind": "GOOGL", "alphabet": "GOOGL",
    "youtube": "GOOGL", "waymo": "GOOGL",
    "meta ai": "META", "llama": "META", "whatsapp": "META",
    "instagram": "META", "facebook": "META", "quest": "META",
    "apple": "AAPL", "iphone": "AAPL", "ios": "AAPL", "vision pro": "AAPL",
    "mac": "AAPL", "apple silicon": "AAPL", "safari": "AAPL",
    "amazon": "AMZN", "aws": "AMZN", "kindle": "AMZN", "alexa": "AMZN",
    "nvidia": "NVDA", "cuda": "NVDA", "blackwell": "NVDA", "h100": "NVDA",
    "amd": "AMD", "ryzen": "AMD", "epyc": "AMD", "rdna": "AMD",
    "intel": "INTC", "xeon": "INTC", "sgx": "INTC",
    "tesla": "TSLA", "cybertruck": "TSLA", "fsd": "TSLA", "dojo": "TSLA",
    "spacex": "",  # private
    "starlink": "",
    "oracle": "ORCL", "cisco": "CSCO", "ibm": "IBM",
    "salesforce": "CRM", "adobe": "ADBE", "snowflake": "SNOW",
    "mongodb": "MDB", "datadog": "DDOG", "confluent": "CFLT",
    "elastic": "ESTC", "cloudflare": "NET", "crowdstrike": "CRWD",
    "palo alto": "PANW", "zscaler": "ZS", "fortinet": "FTNT",
    "netflix": "NFLX", "spotify": "SPOT", "shopify": "SHOP",
    "coinbase": "COIN", "bitcoin": "COIN", "ethereum": "COIN",
    "solana": "COIN", "stablecoin": "COIN",
    "arm": "ARM", "tsmc": "TSM",
    "uber": "UBER", "doordash": "DASH", "airbnb": "ABNB",
    "palantir": "PLTR", "sofi": "SOFI", "robinhood": "HOOD",
    "reddit": "RDDT", "snap": "SNAP", "pinterest": "PINS",
    "databricks": "",  # private
    "stripe": "",
    "ibm watson": "IBM", "redhat": "IBM", "red hat": "IBM",
    "vmware": "AVGO", "broadcom": "AVGO",
    "samsung": "", "huawei": "", "bytedance": "", "tiktok": "",
    "disney": "DIS", "warner": "WBD",
}

TECH_KEYWORDS = {
    "ai": ["ai ", "llm", "gpt", "model", "transformer", "rag",
           "fine-tun", "embedding", "vector db", "chain of thought",
           "reasoning", "agent"],
    "crypto": ["bitcoin", "ethereum", "crypto", "blockchain", "defi",
               "stablecoin", "nft", "solana", "zk", "rollup"],
    "security": ["cve-", "zero-day", "rce", "exploit", "breach",
                 "ransomware", "vulnerability"],
    "quantum": ["quantum", "qubit", "quantum supremacy",
                "post-quantum"],
    "biotech": ["crispr", "gene editing", "mrna", "vaccine",
                "drug trial", "clinical trial", "fda approval"],
    "climate": ["nuclear", "solar", "battery", "ev", "fusion",
                "geothermal", "hydrogen"],
    "robotics": ["robot", "humanoid", "autonomous", "drone",
                 "self-driving"],
}


def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"hnews_attention: {url[:90]}: {e}")
        return None


def _classify(title: str, url: str) -> tuple[str, str]:
    t = f"{title} {url}".lower()
    tickers: set[str] = set()
    for kw, tk in KEYWORD_TICKERS.items():
        if kw in t and tk:
            tickers.add(tk)
    categories: set[str] = set()
    for cat, kws in TECH_KEYWORDS.items():
        if any(k in t for k in kws):
            categories.add(cat)
    return ",".join(sorted(tickers)), ",".join(sorted(categories))


def main() -> None:
    ids = _get_json(f"{BASE}/topstories.json")
    if not isinstance(ids, list) or not ids:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"hnews_attention: no fetch, keeping {OUT_CSV.name}")
        return

    ids = ids[:TOP_N]
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for i, sid in enumerate(ids):
        st = _get_json(f"{BASE}/item/{sid}.json")
        if not isinstance(st, dict):
            continue
        if st.get("type") != "story":
            continue
        title = (st.get("title") or "")[:250]
        url = st.get("url") or ""
        score = int(st.get("score") or 0)
        desc = int(st.get("descendants") or 0)
        ts = int(st.get("time") or 0)
        age_h = (time.time() - ts) / 3600 if ts else 0
        rate = score / age_h if age_h > 0 else 0
        tickers, cats = _classify(title, url)
        rows.append({
            "rank": str(i + 1),
            "hn_id": str(sid),
            "title": title,
            "url": url[:250],
            "score": str(score),
            "comments": str(desc),
            "age_hours": f"{age_h:.2f}",
            "upvote_rate_per_hr": f"{rate:.2f}",
            "by": st.get("by", "")[:40],
            "tickers": tickers,
            "categories": cats,
            "captured_at": now_iso,
        })
        if i % 10 == 9:
            time.sleep(0.15)  # be polite to firebase

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"hnews_attention: empty, keeping {OUT_CSV.name}")
        return

    fieldnames = ["rank", "hn_id", "title", "url", "score", "comments",
                  "age_hours", "upvote_rate_per_hr", "by", "tickers",
                  "categories", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary
    cat_counts: dict[str, int] = {}
    for r in rows:
        for c in r["categories"].split(","):
            if c:
                cat_counts[c] = cat_counts.get(c, 0) + 1
    tick_counts: dict[str, int] = {}
    for r in rows:
        for t in r["tickers"].split(","):
            if t:
                tick_counts[t] = tick_counts.get(t, 0) + 1
    top_cats = " ".join(
        f"{k}={v}" for k, v in
        sorted(cat_counts.items(), key=lambda x: -x[1])[:4])
    top_ticks = " ".join(
        f"{k}={v}" for k, v in
        sorted(tick_counts.items(), key=lambda x: -x[1])[:5])
    print(f"hnews_attention: {len(rows)} stories | cats[{top_cats}] "
          f"| tickers[{top_ticks}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
