#!/usr/bin/env python3
"""post_penny_gap_alert.py — Real-time penny gap-up detector + social poster.

Runs every 30 min during market hours via GitHub Actions price-alert job.
Fetches live Yahoo Finance quotes for the SEC filer universe, detects
gap-ups vs yesterday's close, and fires Twitter + StockTwits posts on
new detections.

Fixes applied:
  1. Proper EDT/EST timezone (DST-aware, not hardcoded UTC-4)
  2. JSON log file deduplication — survives GitHub Actions cache misses
  3. Gap fade check — price must still hold ≥85% of the opening gap

Signal logic (matches ThinkorSwim scanner defaults):
  - Gap ≥ 1% from previous close
  - Price $0.50 – $10 (penny range)
  - Volume ≥ 50K AND volume ratio ≥ 1.5× 30-day avg
  - Gap holding: current price ≥ open × 0.85 (not fading through open)

Required env vars:
  TWITTER_API_KEY / TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN / TWITTER_ACCESS_SECRET
  STOCKTWITS_ACCESS_TOKEN

Optional:
  NEWSLETTER_URL  (defaults to catalystedge.agency)
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# Winner content generator (generates social folder on alert fire)
try:
    from build_winner_content import generate_for_alert as _gen_winner
    _HAS_WINNER_CONTENT = True
except ImportError:
    _HAS_WINNER_CONTENT = False

ROOT           = Path(__file__).parent
PENNY_UNIVERSE = ROOT / "penny_universe.txt"        # broad universe (preferred)
TICKER_FILE    = ROOT / "sec_catalyst_tickers.txt"  # fallback
GAP_TOP_CSV    = ROOT / "gap_scanner_top.csv"
FIRED_LOG      = ROOT / "gap_alerts_fired.json"
ALERT_LOG      = ROOT / "gap_alert_log.csv"       # outcome tracking log
SCANNER_URL    = "catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "catalystedge.agency")

# ── Scanner thresholds ────────────────────────────────────────────────────
GAP_THRESHOLD      = 1.0    # % gap vs previous close
MIN_VOLUME         = 50_000
MIN_VOL_RATIO      = 1.5
MIN_PRICE          = 0.50
MAX_PRICE          = 10.00
FADE_FLOOR         = 0.85   # FIX 3: price must hold ≥85% of opening gap from open
MAX_ALERTS_PER_RUN = 3

# ── Market hours ──────────────────────────────────────────────────────────
PRE_MARKET_OPEN  = dt.time(4,  0)   # pre-market starts 4:00 AM ET
MARKET_OPEN      = dt.time(9, 30)   # regular session
MARKET_CLOSE     = dt.time(16, 0)

# Pre-market volume threshold — lower bar since volume builds through morning
MIN_VOLUME_PREMARKET = 10_000

# ── Yahoo Finance batch quote endpoint ────────────────────────────────────
YAHOO_QUOTE_URL = (
    "https://query1.finance.yahoo.com/v7/finance/quote"
    "?symbols={symbols}"
    "&fields=regularMarketPrice,regularMarketPreviousClose,"
    "regularMarketOpen,regularMarketDayHigh,regularMarketDayLow,"
    "regularMarketVolume,averageDailyVolume3Month,"
    "regularMarketChangePercent,shortName,"
    "preMarketPrice,preMarketChange,preMarketChangePercent,preMarketVolume"
)


# ── FIX 1: DST-aware Eastern Time ────────────────────────────────────────

def et_now() -> dt.datetime:
    """Return current datetime in US Eastern time (EDT or EST)."""
    utc_now = dt.datetime.now(dt.timezone.utc)
    year    = utc_now.year

    # DST starts 2nd Sunday in March, ends 1st Sunday in November
    march    = dt.datetime(year, 3,  1, tzinfo=dt.timezone.utc)
    november = dt.datetime(year, 11, 1, tzinfo=dt.timezone.utc)
    dst_start = march    + dt.timedelta(days=(6 - march.weekday())    % 7 + 7)
    dst_end   = november + dt.timedelta(days=(6 - november.weekday()) % 7)

    offset = -4 if dst_start <= utc_now < dst_end else -5
    return utc_now + dt.timedelta(hours=offset)


def is_premarket() -> bool:
    now = et_now()
    return now.weekday() < 5 and PRE_MARKET_OPEN <= now.time() < MARKET_OPEN


def in_market_hours() -> bool:
    now = et_now()
    return (
        now.weekday() < 5
        and PRE_MARKET_OPEN <= now.time() <= MARKET_CLOSE
    )


# ── FIX 2: JSON log deduplication (survives cache misses) ────────────────

def load_fired() -> dict[str, str]:
    """Load {ticker: date_str} log. Returns empty dict on any error."""
    if not FIRED_LOG.exists():
        return {}
    try:
        return json.loads(FIRED_LOG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_fired(fired: dict[str, str]) -> None:
    today = dt.date.today().isoformat()
    # Prune entries from previous days to keep file small
    pruned = {k: v for k, v in fired.items() if v == today}
    FIRED_LOG.write_text(json.dumps(pruned), encoding="utf-8")


def already_posted(ticker: str, fired: dict[str, str]) -> bool:
    today = dt.date.today().isoformat()
    return fired.get(ticker) == today


def mark_posted(ticker: str, fired: dict[str, str]) -> None:
    fired[ticker] = dt.date.today().isoformat()
    save_fired(fired)


# ── Alert outcome log ─────────────────────────────────────────────────────

def log_alert(gap: dict) -> None:
    """Append alert to gap_alert_log.csv for outcome evaluation at EOD."""
    now_et   = et_now()
    fieldnames = [
        "ticker", "alert_date", "alert_time",
        "alert_price", "prev_close", "gap_pct", "vol_ratio",
    ]
    exists = ALERT_LOG.exists()
    with ALERT_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({
            "ticker":      gap["ticker"],
            "alert_date":  now_et.strftime("%Y-%m-%d"),
            "alert_time":  now_et.strftime("%H:%M"),
            "alert_price": gap["price"],
            "prev_close":  gap["prev_close"],
            "gap_pct":     gap["gap_pct"],
            "vol_ratio":   gap["vol_ratio"],
        })


# ── Yahoo Finance live quotes ─────────────────────────────────────────────

def fetch_quotes(tickers: list[str]) -> list[dict]:
    results: list[dict] = []
    for i in range(0, len(tickers), 80):
        chunk = tickers[i : i + 80]
        url   = YAHOO_QUOTE_URL.format(symbols=",".join(chunk))
        req   = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read())
            results.extend(data.get("quoteResponse", {}).get("result", []))
        except Exception as e:
            print(f"  quote fetch error (chunk {i}): {e}")
        time.sleep(0.3)
    return results


# ── Gap detector ──────────────────────────────────────────────────────────

def detect_gap(q: dict) -> dict | None:
    premarket = is_premarket()

    try:
        prev_close = float(q.get("regularMarketPreviousClose") or 0)
        avg_vol    = float(q.get("averageDailyVolume3Month")   or 1)

        if premarket:
            # Use pre-market price + volume if available
            price  = float(q.get("preMarketPrice")  or 0)
            volume = float(q.get("preMarketVolume") or 0)
            mkt_open  = 0.0   # regular open not set yet in pre-market
            day_high  = price
        else:
            price     = float(q.get("regularMarketPrice")    or 0)
            volume    = float(q.get("regularMarketVolume")   or 0)
            mkt_open  = float(q.get("regularMarketOpen")     or 0)
            day_high  = float(q.get("regularMarketDayHigh")  or price)
    except (TypeError, ValueError):
        return None

    if prev_close <= 0 or price <= 0:
        return None

    # Price filter
    if not (MIN_PRICE <= price <= MAX_PRICE):
        return None

    # Gap vs previous close
    gap_pct = (price - prev_close) / prev_close * 100
    if gap_pct < GAP_THRESHOLD:
        return None

    # Volume filter — lower threshold in pre-market
    vol_min = MIN_VOLUME_PREMARKET if premarket else MIN_VOLUME
    if volume < vol_min:
        return None
    vol_ratio = volume / avg_vol if avg_vol > 0 else 0
    if vol_ratio < MIN_VOL_RATIO:
        return None

    # Gap fade check — only applicable during regular hours (open price exists)
    if not premarket and mkt_open > prev_close:
        gap_open_size = mkt_open - prev_close
        current_retention = (price - prev_close) / gap_open_size
        if current_retention < FADE_FLOOR:
            return None   # gap faded >15% from open — skip

    # Accumulation label
    if vol_ratio >= 5:
        accum = "HEAVY ACCUMULATION 🔥"
    elif vol_ratio >= 3:
        accum = "ELEVATED VOLUME ⚡"
    else:
        accum = "VOLUME SURGE 📈"

    return {
        "ticker":     q.get("symbol", "").upper(),
        "price":      price,
        "prev_close": prev_close,
        "mkt_open":   mkt_open,
        "day_high":   day_high,
        "gap_pct":    round(gap_pct, 1),
        "volume":     int(volume),
        "premarket":  premarket,
        "vol_ratio":  round(vol_ratio, 1),
        "accum":      accum,
        "name":       q.get("shortName", ""),
    }


# ── OAuth 1.0a (Twitter) ──────────────────────────────────────────────────

def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method: str, url: str,
                  consumer_key: str, consumer_secret: str,
                  token: str, token_secret: str) -> str:
    oauth: dict[str, str] = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }
    param_str = "&".join(
        f"{_pct(k)}={_pct(v)}" for k, v in sorted(oauth.items())
    )
    base = f"{method.upper()}&{_pct(url)}&{_pct(param_str)}"
    key  = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig  = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
    )


# ── Twitter post ──────────────────────────────────────────────────────────

def post_twitter(gap: dict) -> bool:
    api_key      = os.environ.get("TWITTER_API_KEY", "")
    api_secret   = os.environ.get("TWITTER_API_SECRET", "")
    token        = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    token_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")
    if not all([api_key, api_secret, token, token_secret]):
        print(f"  twitter: creds missing — skipping {gap['ticker']}")
        return False

    label = "PRE-MARKET GAP ALERT" if gap.get("premarket") else "PENNY GAP ALERT"
    timing = "pre-market move — before regular session opens" if gap.get("premarket") else "catalyst-backed move"
    text = (
        f"🚨 {label} — ${gap['ticker']}\n\n"
        f"💰 ${gap['price']:.2f}  (+{gap['gap_pct']:.1f}% gap)\n"
        f"📊 {gap['accum']} ({gap['vol_ratio']:.1f}× avg vol)\n"
        f"📋 {timing}\n\n"
        f"🖥️ {SCANNER_URL}\n"
        f"📬 {NEWSLETTER_URL}\n"
        f"#{gap['ticker']} #PennyStocks #GapUp #PreMarket #CatalystEdge"
    )

    url  = "https://api.twitter.com/2/tweets"
    body = json.dumps({"text": text}).encode()
    auth = _oauth_header("POST", url, api_key, api_secret, token, token_secret)
    req  = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": auth,
            "Content-Type":  "application/json",
            "User-Agent":    "CatalystEdge/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        tid = result.get("data", {}).get("id", "?")
        print(f"  twitter ✓ {gap['ticker']} — tweet {tid}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  twitter ✗ {gap['ticker']}: {e.code} {e.read()[:200]}")
        return False
    except Exception as e:
        print(f"  twitter ✗ {gap['ticker']}: {e}")
        return False


# ── Telegram alert ────────────────────────────────────────────────────────

def post_telegram_alert(gap: dict) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel = os.environ.get("TELEGRAM_CHANNEL", "")
    if not token or not channel:
        return False
    label   = "🌙 PRE-MARKET GAP ALERT" if gap.get("premarket") else "🚨 PENNY GAP ALERT"
    sign    = "+" if gap["gap_pct"] >= 0 else ""
    text = (
        f"{label}\n\n"
        f"*${gap['ticker']}* — ${gap['price']:.2f}  ({sign}{gap['gap_pct']:.1f}% gap)\n"
        f"{gap['vol_ratio']:.1f}× average volume | {gap.get('accum','')}\n\n"
        f"🖥️ Scanner → {SCANNER_URL}\n"
        f"📧 Newsletter → {NEWSLETTER_URL}\n"
        f"📲 More alerts → @CatalystEdgePro\n"
        f"#pennystocks #gapup #daytrading"
    )
    payload = json.dumps({
        "chat_id": channel, "text": text, "parse_mode": "Markdown"
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print(f"  telegram ✓ {gap['ticker']}")
            return True
        print(f"  telegram ✗ {gap['ticker']}: {result.get('description','')}")
        return False
    except Exception as e:
        print(f"  telegram ✗ {gap['ticker']}: {e}")
        return False


# ── StockTwits post ────────────────────────────────────────────────────────

def post_stocktwits(gap: dict) -> bool:
    token = os.environ.get("STOCKTWITS_ACCESS_TOKEN", "")
    if not token:
        print(f"  stocktwits: token missing — skipping {gap['ticker']}")
        return False

    label   = "PRE-MARKET GAP ALERT" if gap.get("premarket") else "PENNY GAP ALERT"
    context = "Pre-market move — watch for continuation at open." if gap.get("premarket") else "High-risk / high-reward setup."
    body = (
        f"${gap['ticker']} 🚨 {label}\n\n"
        f"${gap['price']:.2f}  (+{gap['gap_pct']:.1f}% gap vs yesterday close)\n"
        f"{gap['accum']} — {gap['vol_ratio']:.1f}× average volume\n\n"
        f"{context}\n"
        f"Full breakdown → {SCANNER_URL}"
    )

    data = urllib.parse.urlencode({
        "access_token": token,
        "body":         body,
        "sentiment":    "Bullish",
    }).encode()

    req = urllib.request.Request(
        "https://api.stocktwits.com/api/2/messages/create.json",
        data=data,
        headers={"User-Agent": "CatalystEdge/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        mid = result.get("message", {}).get("id", "?")
        print(f"  stocktwits ✓ {gap['ticker']} — msg {mid}")
        return True
    except urllib.error.HTTPError as e:
        print(f"  stocktwits ✗ {gap['ticker']}: {e.code} {e.read()[:200]}")
        return False
    except Exception as e:
        print(f"  stocktwits ✗ {gap['ticker']}: {e}")
        return False


# ── Ticker loader ─────────────────────────────────────────────────────────

def load_tickers() -> list[str]:
    tickers: list[str] = []
    seen:    set[str]  = set()

    if GAP_TOP_CSV.exists():
        try:
            with GAP_TOP_CSV.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    t = row.get("ticker", "").strip().upper()
                    if t and t not in seen:
                        tickers.append(t)
                        seen.add(t)
        except Exception:
            pass

    # Use broad penny universe if available, fallback to SEC filers
    universe = PENNY_UNIVERSE if PENNY_UNIVERSE.exists() else TICKER_FILE
    if universe.exists():
        with universe.open(encoding="utf-8") as f:
            for line in f:
                t = line.strip().upper()
                if t and t not in seen:
                    tickers.append(t)
                    seen.add(t)

    return tickers


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    if not in_market_hours():
        now_et = et_now()
        print(f"post_penny_gap_alert: outside market hours ({now_et.strftime('%H:%M ET')}) — skipping")
        return 0

    tickers = load_tickers()
    if not tickers:
        print("post_penny_gap_alert: no tickers to scan")
        return 0

    print(f"post_penny_gap_alert: scanning {len(tickers)} tickers @ {et_now().strftime('%H:%M ET')}...")

    fired  = load_fired()
    quotes = fetch_quotes(tickers)
    gaps   = []

    for q in quotes:
        g = detect_gap(q)
        if g and not already_posted(g["ticker"], fired):
            gaps.append(g)

    gaps.sort(key=lambda x: -x["gap_pct"])

    if not gaps:
        print("  no new penny gaps detected this window")
        return 0

    print(f"  {len(gaps)} new gap(s) — posting top {min(len(gaps), MAX_ALERTS_PER_RUN)}")

    posted = 0
    for gap in gaps:
        if posted >= MAX_ALERTS_PER_RUN:
            break
        print(f"\n  → {gap['ticker']}  ${gap['price']:.2f}  +{gap['gap_pct']:.1f}%  {gap['vol_ratio']:.1f}×vol  open=${gap['mkt_open']:.2f}")
        tw = post_twitter(gap)
        st = post_stocktwits(gap)
        post_telegram_alert(gap)
        if tw or st:
            mark_posted(gap["ticker"], fired)
            log_alert(gap)
            if _HAS_WINNER_CONTENT:
                try:
                    _gen_winner(gap)
                except Exception as exc:
                    print(f"  winner_content skipped for {gap['ticker']}: {exc}")
            posted += 1
        time.sleep(2)

    print(f"\npost_penny_gap_alert: {posted} alert(s) posted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
