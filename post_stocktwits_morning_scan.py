#!/usr/bin/env python3
"""post_stocktwits_morning_scan.py — Pre-market watchlist post to StockTwits.

Runs at 9:25 AM ET (before open). Posts a single consolidated pre-market
watchlist message showing all gap scanner tickers with pre-market prices.
This creates daily trader ritual and builds following on StockTwits.

Each ticker in the message creates a clickable cashtag that appears in that
ticker's stream — maximum organic reach across all tracked stocks.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
GAP_CSV        = ROOT / "gap_scanner_top.csv"
PENNY_FILE     = ROOT / "penny_universe.txt"
SEC_FILE       = ROOT / "sec_catalyst_tickers.txt"
SCANNER_URL    = "catalystedgescanner.com"
NEWSLETTER_URL = "catalystedge.agency"
API_BASE       = "https://api.stocktwits.com/api/2"
MAX_TICKERS    = 10

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?interval=1m&range=1d&prePost=true"
)


def get_token() -> str:
    token = os.getenv("STOCKTWITS_ACCESS_TOKEN", "").strip()
    if not token:
        env_file = ROOT / ".sec_email_env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("STOCKTWITS_ACCESS_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    if not token:
        print("post_stocktwits_morning_scan: no token — skipping")
        raise SystemExit(0)
    return token


def et_now() -> dt.datetime:
    utc      = dt.datetime.now(dt.timezone.utc)
    march    = dt.datetime(utc.year, 3,  1, tzinfo=dt.timezone.utc)
    november = dt.datetime(utc.year, 11, 1, tzinfo=dt.timezone.utc)
    dst_start = march    + dt.timedelta(days=(6 - march.weekday())    % 7 + 7)
    dst_end   = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    offset = -4 if dst_start <= utc < dst_end else -5
    return utc + dt.timedelta(hours=offset)


def load_tickers() -> list[str]:
    tickers = []
    if GAP_CSV.exists():
        try:
            with GAP_CSV.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker", "").strip().upper()
                    if t:
                        tickers.append(t)
        except Exception:
            pass
    if tickers:
        return tickers[:MAX_TICKERS]
    src = PENNY_FILE if PENNY_FILE.exists() else SEC_FILE
    if src.exists():
        with src.open(encoding="utf-8") as f:
            for line in f:
                t = line.strip().upper()
                if t:
                    tickers.append(t)
    return tickers[:MAX_TICKERS]


def fetch_quote(symbol: str) -> dict | None:
    url = YAHOO_URL.format(symbol=symbol.upper())
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        meta   = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        price  = next((c for c in reversed(closes) if c is not None),
                      meta.get("regularMarketPrice", 0))
        prev   = meta.get("chartPreviousClose") or price
        chg    = ((price - prev) / prev * 100) if prev else 0
        return {"price": price, "chg": chg}
    except Exception:
        return None


def build_message(tickers: list[str], now_et: dt.datetime) -> str:
    date_str = now_et.strftime("%b %-d")
    lines = [f"⚡ PRE-MARKET GAP SCAN — {date_str}", ""]
    lines.append(f"Top {len(tickers)} plays from 1,600+ ticker scan:")
    lines.append("")

    for ticker in tickers:
        q = fetch_quote(ticker)
        if q and q["price"] > 0:
            sign = "+" if q["chg"] >= 0 else ""
            icon = "🔥" if q["chg"] >= 20 else "📈" if q["chg"] >= 5 else "➡️"
            lines.append(f"{icon} ${ticker}  ${q['price']:.2f}  {sign}{q['chg']:.1f}%")
        else:
            lines.append(f"📊 ${ticker}")
        time.sleep(0.2)

    lines.extend([
        "",
        f"🖥️ Live scanner → {SCANNER_URL}",
        f"📧 Newsletter → {NEWSLETTER_URL}",
        f"📲 Live alerts → t.me/CatalystEdgePro",
        "#pennystocks #premarket #gapup #daytrading #fintwit",
    ])
    return "\n".join(lines)[:1000]


def post_message(token: str, message: str) -> bool:
    data = urllib.parse.urlencode({
        "access_token": token,
        "body":         message,
        "sentiment":    "Bullish",
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/messages/create.json",
        data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        mid = result.get("message", {}).get("id", "?")
        print(f"  ✅ StockTwits morning scan posted — id={mid}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  ❌ StockTwits error: {e.code} {e.read()[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ StockTwits error: {e}")
        return False


def main() -> int:
    now_et = et_now()

    # Only run on weekdays before market open
    if now_et.weekday() >= 5:
        print("post_stocktwits_morning_scan: weekend — skipping")
        return 0

    # Gate: once per day
    stamp = now_et.date().isoformat()
    flag  = ROOT / f".stocktwits_scan_{stamp}"
    if flag.exists():
        print(f"post_stocktwits_morning_scan: already posted {stamp} — skipping")
        return 0

    token   = get_token()
    tickers = load_tickers()
    if not tickers:
        print("post_stocktwits_morning_scan: no tickers — skipping")
        return 0

    print(f"post_stocktwits_morning_scan: building scan for {len(tickers)} tickers")
    message = build_message(tickers, now_et)
    print(f"\n{message}\n")

    if post_message(token, message):
        flag.touch()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
