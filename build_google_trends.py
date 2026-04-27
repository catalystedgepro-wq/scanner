#!/usr/bin/env python3
"""build_google_trends.py — Retail search-attention proxy via Wikipedia pageviews.

Google Trends has no official free API and heavily rate-limits unofficial
clients. Wikipedia pageviews are free, official, and highly correlated with
search-engine attention on a stock.

Source: Wikimedia pageviews REST API
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
Pulls 30-day daily view counts per ticker's Wikipedia article and computes
z-score spike vs. 30-day baseline.

Output: google_trends.csv
Columns: ticker, wiki_article, latest_views, avg_30d, z_score, spike_pct
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
import urllib.parse
import time
import math
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "google_trends.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

# Tracked tickers: pull from universe_gravity if present, else use a core set.
UNIVERSE = ROOT / "universe_gravity.csv"
CORE = [
    ("TSLA", "Tesla,_Inc."), ("NVDA", "Nvidia"), ("AAPL", "Apple_Inc."),
    ("MSFT", "Microsoft"), ("META", "Meta_Platforms"), ("AMZN", "Amazon_(company)"),
    ("GOOGL", "Alphabet_Inc."), ("AMD", "Advanced_Micro_Devices"),
    ("PLTR", "Palantir_Technologies"), ("GME", "GameStop"),
    ("AMC", "AMC_Theatres"), ("COIN", "Coinbase"),
    ("HOOD", "Robinhood_Markets"), ("SOFI", "SoFi"),
    ("MSTR", "Strategy_(company)"), ("RIVN", "Rivian"),
    ("LCID", "Lucid_Group"), ("NIO", "Nio_Inc."),
    ("INTC", "Intel"), ("MU", "Micron_Technology"),
    ("BABA", "Alibaba_Group"), ("BIDU", "Baidu"),
    ("MARA", "Marathon_Digital_Holdings"),
    ("RIOT", "Riot_Platforms"), ("CLSK", "CleanSpark"),
    ("SMCI", "Super_Micro_Computer"), ("AI", "C3.ai"),
    ("SNOW", "Snowflake_Inc."), ("NET", "Cloudflare"),
    ("CRWD", "CrowdStrike"),
]

API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia.org/all-access/user/{article}/daily/{start}/{end}"
)


def fetch(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"trends: {url[-40:]} -> {e}")
        return None


def main():
    today = dt.date.today()
    end = today.strftime("%Y%m%d")
    start = (today - dt.timedelta(days=30)).strftime("%Y%m%d")
    rows = []
    for tic, article in CORE:
        u = API.format(article=urllib.parse.quote(article, safe=""), start=start, end=end)
        data = fetch(u)
        if not data or "items" not in data:
            time.sleep(0.3)
            continue
        pts = data["items"]
        if not pts:
            continue
        latest = int(pts[-1].get("views") or 0)
        baseline = [int(p.get("views") or 0) for p in pts[:-1]]
        if not baseline:
            continue
        mean = sum(baseline) / len(baseline)
        var = sum((x - mean) ** 2 for x in baseline) / len(baseline)
        stdev = math.sqrt(var) if var > 0 else 1
        z = (latest - mean) / stdev if stdev else 0
        spike_pct = ((latest - mean) / mean * 100) if mean else 0
        rows.append({
            "ticker": tic,
            "wiki_article": article,
            "latest_views": latest,
            "avg_30d": f"{mean:.0f}",
            "z_score": f"{z:.2f}",
            "spike_pct": f"{spike_pct:+.0f}",
        })
        time.sleep(0.25)
    rows.sort(key=lambda r: float(r["z_score"]), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "wiki_article", "latest_views",
                "avg_30d", "z_score", "spike_pct",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"google_trends: {len(rows)} tickers -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
