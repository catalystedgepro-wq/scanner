#!/usr/bin/env python3
"""build_wiki_attention.py — Wikipedia pageviews as retail attention proxy.

Academic finance: Da/Engelberg/Gao 2011 "In Search of Attention" showed
retail attention (measured by Google SVI) predicts short-term stock
returns + reverses within 1 year. Wikipedia pageviews = cleaner,
rate-limited-free, public alternative with same signal.

Trade uses:
- Pageview spike > 2σ above 30-day mean: retail-driven move imminent
  (gamma squeeze setup, meme-stock rotation candidate).
- Coordinated spike across sector peers (NVDA + AMD + AVGO): sector
  rotation, not idiosyncratic — chase the ETF (SMH/SOXX) instead.
- Pageview decay after earnings run-up: sell-the-news setup, fade
  continuation longs.
- New-high pageviews with flat/down price: distribution (smart money
  selling into retail attention).

Source: wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/
all-access/all-agents/{article}/daily/{start}/{end}. Public, no key,
3 req/sec guideline.

Output: wiki_attention.csv
Columns: date, ticker, article, views, mean_30d, sigma_30d, z_score,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "wiki_attention.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}"
)

# Ticker → Wikipedia article slug. Focus on names where retail attention
# moves price: mega-cap tech, meme candidates, sector bellwethers.
TICKERS = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "GOOGL": "Google",
    "AMZN": "Amazon_(company)",
    "META": "Meta_Platforms",
    "TSLA": "Tesla,_Inc.",
    "AMD": "AMD",
    "AVGO": "Broadcom",
    "NFLX": "Netflix",
    "DIS": "The_Walt_Disney_Company",
    "JPM": "JPMorgan_Chase",
    "BAC": "Bank_of_America",
    "XOM": "ExxonMobil",
    "CVX": "Chevron_Corporation",
    "PLTR": "Palantir_Technologies",
    "COIN": "Coinbase",
    "SMCI": "Supermicro",
    "GME": "GameStop",
    "AMC": "AMC_Theatres",
    "BABA": "Alibaba_Group",
    "UBER": "Uber",
    "ABNB": "Airbnb",
    "SHOP": "Shopify",
    "NKE": "Nike,_Inc.",
    "WMT": "Walmart",
    "TGT": "Target_Corporation",
    "COST": "Costco",
    "HD": "The_Home_Depot",
    "BA": "Boeing",
}


def wiki_fetch(article: str, start: dt.date, end: dt.date) -> list[tuple[str, int]]:
    """Returns [(YYYY-MM-DD, views)] for a Wikipedia article."""
    url = API.format(
        article=urllib.parse.quote(article, safe=""),
        start=start.strftime("%Y%m%d") + "00",
        end=end.strftime("%Y%m%d") + "00",
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"wiki_attention {article}: {e}")
        return []
    out: list[tuple[str, int]] = []
    for item in payload.get("items", []):
        ts = item.get("timestamp", "")
        if len(ts) >= 8:
            ymd = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
            try:
                out.append((ymd, int(item.get("views", 0))))
            except (ValueError, TypeError):
                continue
    return out


def zscore(series: list[int]) -> tuple[float, float]:
    """(mean, stdev) with stdev=0 guard."""
    if not series:
        return 0.0, 0.0
    m = sum(series) / len(series)
    v = sum((x - m) ** 2 for x in series) / len(series)
    return m, math.sqrt(v)


def main() -> None:
    end = dt.date.today()
    start = end - dt.timedelta(days=45)  # need 30 for baseline + ~15 emit
    rows: list[dict] = []
    for ticker, article in TICKERS.items():
        series = wiki_fetch(article, start, end)
        if len(series) < 20:
            continue
        series.sort()
        dates = [d for d, _ in series]
        views = [v for _, v in series]
        # Emit last ~15 days; compute z-score over prior 30-day window.
        for i in range(len(series)):
            if i < 30:
                continue
            window = views[i - 30:i]
            m, sd = zscore(window)
            if sd <= 0:
                z = 0.0
            else:
                z = (views[i] - m) / sd
            rows.append({
                "date": dates[i],
                "ticker": ticker,
                "article": article,
                "views": views[i],
                "mean_30d": f"{m:.0f}",
                "sigma_30d": f"{sd:.0f}",
                "z_score": f"{z:.2f}",
            })
        time.sleep(0.35)  # Respect 3/sec Wikimedia guideline
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 120:
        print(f"wiki_attention: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "ticker", "article", "views",
                        "mean_30d", "sigma_30d", "z_score", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    # Spotlight latest z-score movers.
    rows.sort(key=lambda r: (r["date"], abs(float(r["z_score"] or "0"))),
              reverse=True)
    top = rows[:3] if rows else []
    spot = " | ".join(
        f"{r['ticker']} z={r['z_score']}" for r in top
    )
    print(f"wiki_attention: {len(rows)} rows "
          f"({len({r['ticker'] for r in rows})} tickers) "
          f"latest movers: {spot} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
